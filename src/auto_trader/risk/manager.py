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


@dataclass
class RiskState:
    current_dd_pct: float = 0.0
    portfolio_exposure_pct: float = 0.0
    concentration_score: float = 0.0
    correlated_exposure_pct: float = 0.0
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
    ) -> dict[str, object]:
        dd_pct = _dd_pct(current_equity, equity_peak)
        self.state.current_dd_pct = dd_pct
        self.state.portfolio_exposure_pct = portfolio_exposure_pct
        self.state.concentration_score = concentration_score
        self.state.correlated_exposure_pct = correlated_exposure_pct

        codes: list[str] = []
        blocked = False

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
        if not codes:
            codes.append("RISK_OK")

        return {
            "timestamp": timestamp.astimezone(UTC),
            "symbol": symbol,
            "risk_blocked": blocked,
            "block_reason_codes": sorted(set(codes)),
            "current_dd_pct": dd_pct,
            "portfolio_exposure_pct": portfolio_exposure_pct,
            "concentration_score": concentration_score,
            "correlated_exposure_pct": correlated_exposure_pct,
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
    has_correlated_exposure = "correlated_exposure_pct" in risk_inputs.columns
    for row in risk_inputs.itertuples(index=False):
        out = manager.evaluate(
            timestamp=_to_datetime_utc(row.timestamp),
            symbol=str(row.symbol),
            current_equity=_to_float(row.current_equity),
            equity_peak=_to_float(row.equity_peak),
            symbol_exposure_pct=_to_float(row.symbol_exposure_pct),
            portfolio_exposure_pct=_to_float(row.portfolio_exposure_pct),
            concentration_score=_to_float(row.concentration_score),
            correlated_exposure_pct=_to_float(row.correlated_exposure_pct)
            if has_correlated_exposure
            else 0.0,
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

    grouped = out.groupby("timestamp", dropna=False)["_symbol_exposure_pct_num"].apply(
        lambda s: float(s.nlargest(2).sum())
    )
    out["correlated_exposure_pct"] = out["timestamp"].map(grouped).fillna(0.0).astype(float)
    out = out.drop(columns=["_symbol_exposure_pct_num"])
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
