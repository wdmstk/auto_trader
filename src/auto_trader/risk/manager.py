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


@dataclass
class RiskState:
    current_dd_pct: float = 0.0
    portfolio_exposure_pct: float = 0.0
    concentration_score: float = 0.0
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
    ) -> dict[str, object]:
        dd_pct = _dd_pct(current_equity, equity_peak)
        self.state.current_dd_pct = dd_pct
        self.state.portfolio_exposure_pct = portfolio_exposure_pct
        self.state.concentration_score = concentration_score

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
    for row in risk_inputs.itertuples(index=False):
        out = manager.evaluate(
            timestamp=_to_datetime_utc(row.timestamp),
            symbol=str(row.symbol),
            current_equity=_to_float(row.current_equity),
            equity_peak=_to_float(row.equity_peak),
            symbol_exposure_pct=_to_float(row.symbol_exposure_pct),
            portfolio_exposure_pct=_to_float(row.portfolio_exposure_pct),
            concentration_score=_to_float(row.concentration_score),
        )
        rows.append(out)
    return pd.DataFrame(rows)


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
