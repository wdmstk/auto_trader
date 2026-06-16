from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import pandas as pd


@dataclass(frozen=True)
class RiskConfig:
    max_dd_pct: float = 15.0
    max_symbol_exposure_pct: float = 25.0
    max_portfolio_exposure_pct: float = 70.0
    max_concentration_score: float = 0.6
    max_correlated_exposure_pct: float = 50.0
    soft_vol_weighted_exposure_pct: float = 45.0
    max_vol_weighted_exposure_pct: float = 60.0
    max_risk_contribution_pct: float = 55.0
    min_size_scale: float = 0.25
    fallback_size_scale_missing_vol: float = 0.5
    max_missing_vol_ratio: float = 0.2


@dataclass
class RiskState:
    current_dd_pct: float = 0.0
    portfolio_exposure_pct: float = 0.0
    concentration_score: float = 0.0
    correlated_exposure_pct: float = 0.0
    vol_weighted_exposure_pct: float = 0.0
    emergency_state: bool = False


class RiskManager:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()
        self.state = RiskState()

    def evaluate(
        self,
        *,
        timestamp: datetime,
        symbol: str,
        current_equity: float,
        equity_peak: float,
        symbol_exposure_pct: float,
        portfolio_exposure_pct: float,
        concentration_score: float,
        correlated_exposure_pct: float = 0.0,
        vol_weighted_exposure_pct: float = 0.0,
        risk_contribution_pct: float = 0.0,
        missing_vol_ratio: float = 0.0,
    ) -> dict[str, object]:
        dd_pct = _dd_pct(current_equity, equity_peak)
        self.state.current_dd_pct = dd_pct
        self.state.portfolio_exposure_pct = portfolio_exposure_pct
        self.state.concentration_score = concentration_score
        self.state.correlated_exposure_pct = correlated_exposure_pct
        self.state.vol_weighted_exposure_pct = vol_weighted_exposure_pct

        codes: list[str] = []
        blocked = False
        size_scale = 1.0

        if self.state.emergency_state:
            blocked = True
            codes.append("RISK_EMERGENCY_STOP")
        if dd_pct > self.config.max_dd_pct:
            blocked = True
            codes.append("RISK_DD_LIMIT")
        if symbol_exposure_pct > self.config.max_symbol_exposure_pct:
            blocked = True
            codes.append("RISK_SYMBOL_EXPOSURE")
        if portfolio_exposure_pct > self.config.max_portfolio_exposure_pct:
            blocked = True
            codes.append("RISK_PORTFOLIO_EXPOSURE")
        if concentration_score > self.config.max_concentration_score:
            blocked = True
            codes.append("RISK_CONCENTRATION")
        if correlated_exposure_pct > self.config.max_correlated_exposure_pct:
            blocked = True
            codes.append("RISK_CORRELATED_EXPOSURE")
        if missing_vol_ratio >= self.config.max_missing_vol_ratio:
            blocked = True
            codes.append("RISK_VOL_WEIGHTED_EXPOSURE")
            codes.append("RISK_VOL_MISSING")
        elif missing_vol_ratio > 0.0:
            size_scale = min(size_scale, self.config.fallback_size_scale_missing_vol)

        if vol_weighted_exposure_pct > self.config.max_vol_weighted_exposure_pct:
            blocked = True
            codes.append("RISK_VOL_WEIGHTED_EXPOSURE")
        elif vol_weighted_exposure_pct > self.config.soft_vol_weighted_exposure_pct:
            scaled = self.config.soft_vol_weighted_exposure_pct / max(vol_weighted_exposure_pct, 1e-9)
            size_scale = min(size_scale, max(self.config.min_size_scale, scaled))

        if risk_contribution_pct > self.config.max_risk_contribution_pct:
            blocked = True
            codes.append("RISK_RISK_CONTRIBUTION")
            scaled = self.config.max_risk_contribution_pct / max(risk_contribution_pct, 1e-9)
            size_scale = min(size_scale, max(self.config.min_size_scale, scaled))
        if not codes:
            codes.append("RISK_OK")

        return {
            "timestamp": timestamp.astimezone(UTC).isoformat(),
            "symbol": symbol,
            "risk_blocked": blocked,
            "block_reason_codes": sorted(set(codes)),
            "current_dd_pct": dd_pct,
            "portfolio_exposure_pct": portfolio_exposure_pct,
            "concentration_score": concentration_score,
            "correlated_exposure_pct": correlated_exposure_pct,
            "vol_weighted_exposure_pct": vol_weighted_exposure_pct,
            "risk_contribution_pct": risk_contribution_pct,
            "missing_vol_ratio": missing_vol_ratio,
            "size_scale": size_scale if not blocked else 0.0,
            "emergency_state": self.state.emergency_state,
        }

    def emergency_stop(self) -> None:
        self.state.emergency_state = True

    def emergency_resume(self) -> None:
        self.state.emergency_state = False


def _dd_pct(current_equity: float, equity_peak: float) -> float:
    if equity_peak <= 0:
        return 0.0
    return ((equity_peak - current_equity) / equity_peak) * 100.0


def build_concentration_score(exposures: dict[str, float]) -> float:
    # Simple concentration proxy: max exposure share over total exposure.
    values = [v for k, v in exposures.items() if k.endswith("_exposure_pct")]
    if not values:
        return 0.0
    total = sum(values)
    if total <= 0:
        return 0.0
    return max(values) / total


def evaluate_portfolio_risk(
    *,
    manager: RiskManager,
    risk_inputs: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    inputs = ensure_volatility_risk_columns(ensure_correlated_exposure_column(risk_inputs))
    has_correlated_exposure = "correlated_exposure_pct" in inputs.columns
    has_vwe = "vol_weighted_exposure_pct" in inputs.columns
    has_rc = "risk_contribution_pct" in inputs.columns
    has_mv = "missing_vol_ratio" in inputs.columns
    timestamps = inputs["timestamp"].to_numpy(copy=False)
    symbols = inputs["symbol"].astype(str).to_numpy(copy=False)
    current_equity = inputs["current_equity"].astype(float).to_numpy(copy=False)
    equity_peak = inputs["equity_peak"].astype(float).to_numpy(copy=False)
    symbol_exposure = inputs["symbol_exposure_pct"].astype(float).to_numpy(copy=False)
    portfolio_exposure = inputs["portfolio_exposure_pct"].astype(float).to_numpy(copy=False)
    concentration = inputs["concentration_score"].astype(float).to_numpy(copy=False)
    correlated = inputs["correlated_exposure_pct"].astype(float).to_numpy(copy=False) if has_correlated_exposure else None
    vol_weighted = inputs["vol_weighted_exposure_pct"].astype(float).to_numpy(copy=False) if has_vwe else None
    risk_contribution = inputs["risk_contribution_pct"].astype(float).to_numpy(copy=False) if has_rc else None
    missing_vol = inputs["missing_vol_ratio"].astype(float).to_numpy(copy=False) if has_mv else None

    for i in range(len(inputs)):
        out = manager.evaluate(
            timestamp=_to_datetime_utc(timestamps[i]),
            symbol=str(symbols[i]),
            current_equity=float(current_equity[i]),
            equity_peak=float(equity_peak[i]),
            symbol_exposure_pct=float(symbol_exposure[i]),
            portfolio_exposure_pct=float(portfolio_exposure[i]),
            concentration_score=float(concentration[i]),
            correlated_exposure_pct=float(correlated[i]) if correlated is not None else 0.0,
            vol_weighted_exposure_pct=float(vol_weighted[i]) if vol_weighted is not None else 0.0,
            risk_contribution_pct=float(risk_contribution[i]) if risk_contribution is not None else 0.0,
            missing_vol_ratio=float(missing_vol[i]) if missing_vol is not None else 0.0,
        )
        rows.append(out)
    return pd.DataFrame(rows)


def ensure_correlated_exposure_column(risk_inputs: pd.DataFrame) -> pd.DataFrame:
    if "correlated_exposure_pct" in risk_inputs.columns:
        return risk_inputs
    if risk_inputs.empty:
        out = risk_inputs.copy()
        out["correlated_exposure_pct"] = pd.Series(dtype="float64")
        return out

    required = {"timestamp", "symbol_exposure_pct"}
    if not required.issubset(risk_inputs.columns):
        out = risk_inputs.copy()
        out["correlated_exposure_pct"] = 0.0
        return out

    out = risk_inputs.copy()
    out["_symbol_exposure_pct_num"] = pd.to_numeric(
        out["symbol_exposure_pct"],
        errors="coerce",
    ).fillna(0.0)

    grouped = out.groupby("timestamp", dropna=False)["_symbol_exposure_pct_num"].nlargest(2).groupby(level=0).sum().astype(float)
    out["correlated_exposure_pct"] = out["timestamp"].map(grouped).fillna(0.0).astype(float)
    out = out.drop(columns=["_symbol_exposure_pct_num"])
    return out


def ensure_volatility_risk_columns(risk_inputs: pd.DataFrame) -> pd.DataFrame:
    out = risk_inputs.copy()
    if out.empty:
        out["vol_weighted_exposure_pct"] = pd.Series(dtype="float64")
        out["risk_contribution_pct"] = pd.Series(dtype="float64")
        out["missing_vol_ratio"] = pd.Series(dtype="float64")
        return out

    required = {"timestamp", "symbol_exposure_pct"}
    if not required.issubset(out.columns):
        out["vol_weighted_exposure_pct"] = 0.0
        out["risk_contribution_pct"] = 0.0
        out["missing_vol_ratio"] = 1.0
        return out

    vol_col = next((c for c in ["volatility", "rolling_volatility", "vol"] if c in out.columns), None)
    if vol_col is None:
        if "portfolio_exposure_pct" in out.columns:
            vwe = pd.to_numeric(out["portfolio_exposure_pct"], errors="coerce").fillna(0.0)
        else:
            vwe = pd.Series(0.0, index=out.index, dtype="float64")
        out["vol_weighted_exposure_pct"] = vwe.astype(float)
        out["risk_contribution_pct"] = 0.0
        out["missing_vol_ratio"] = 1.0
        return out

    out["_exp"] = pd.to_numeric(out["symbol_exposure_pct"], errors="coerce").fillna(0.0).clip(lower=0.0)
    out["_vol"] = pd.to_numeric(out[vol_col], errors="coerce")
    out["_vol_missing"] = out["_vol"].isna().astype(float)

    by_ts = out.groupby("timestamp", dropna=False)
    vol_med = by_ts["_vol"].transform("median").fillna(1.0).clip(lower=1e-9)
    out["_vol_filled"] = out["_vol"].fillna(vol_med).clip(lower=1e-9)
    out["_vol_factor"] = out["_vol_filled"] / vol_med
    out["_weighted_exp"] = out["_exp"] * out["_vol_factor"]
    weighted_tot = by_ts["_weighted_exp"].transform("sum").fillna(0.0)
    out["vol_weighted_exposure_pct"] = weighted_tot
    out["risk_contribution_pct"] = 0.0
    valid = weighted_tot > 0
    out.loc[valid, "risk_contribution_pct"] = (out.loc[valid, "_weighted_exp"] / weighted_tot.loc[valid]) * 100.0
    out["missing_vol_ratio"] = by_ts["_vol_missing"].transform("mean").fillna(1.0)
    drop_cols = ["_exp", "_vol", "_vol_missing", "_vol_filled", "_vol_factor", "_weighted_exp"]
    out = out.drop(columns=[c for c in drop_cols if c in out.columns])
    return out


def _to_float(v: object) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _to_datetime_utc(v: object) -> datetime:
    ts = pd.Timestamp(cast(Any, v))
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    dt = ts.to_pydatetime()
    if not isinstance(dt, datetime):
        raise TypeError("timestamp conversion failed")
    return dt
