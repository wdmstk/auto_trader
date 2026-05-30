from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd


@dataclass(frozen=True)
class TrendStrategyConfig:
    breakout_persistence_min: float = 0.6
    momentum_persistence_min: float = 0.5
    pullback_shallowness_min: float = 0.5
    higher_high_persistence_min: float = 0.5
    trend_efficiency_exit_threshold: float = 0.1
    default_position_size_ratio: float = 0.1
    max_add_count: int = 2


def generate_trend_signals(
    *,
    features_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    risk_df: pd.DataFrame | None = None,
    pnl_df: pd.DataFrame | None = None,
    config: TrendStrategyConfig | None = None,
) -> pd.DataFrame:
    cfg = config or TrendStrategyConfig()
    merged = _merge_inputs(features_df, regime_df, risk_df, pnl_df)
    merged = merged.sort_values(["symbol", "timeframe", "timestamp"]).reset_index(drop=True)

    entry_signal: list[bool] = []
    exit_signal: list[bool] = []
    add_signal: list[bool] = []
    risk_blocked: list[bool] = []
    reason_codes: list[list[str]] = []
    position_size_ratio: list[float] = []

    current_add_count = 0
    in_position = False

    for _, row in merged.iterrows():
        reasons: list[str] = []
        blocked = bool(row["risk_blocked"])
        high_vol = (str(row["regime"]) == "HIGH_VOL") or (not bool(row["is_trade_allowed"]))

        if high_vol:
            reasons.append("TR_BLOCK_HIGH_VOL")
        if blocked:
            reasons.append("TR_BLOCK_RISK_LIMIT")

        regime_ok = str(row["regime"]) == "TREND" and bool(row["is_trade_allowed"])
        gate_ok = regime_ok and (not high_vol) and (not blocked)

        breakout_ok = _f(row["breakout_persistence"]) >= cfg.breakout_persistence_min
        momentum_ok = _f(row["momentum_persistence"]) >= cfg.momentum_persistence_min
        pullback_ok = _f(row["pullback_shallowness"]) >= cfg.pullback_shallowness_min
        higher_high_ok = _f(row["higher_high_persistence"]) >= cfg.higher_high_persistence_min

        entry = gate_ok and breakout_ok and momentum_ok and pullback_ok and higher_high_ok
        if entry:
            reasons.extend(
                [
                    "TR_ENTRY_BREAKOUT_PERSIST",
                    "TR_ENTRY_MOMENTUM_PERSIST",
                    "TR_ENTRY_PULLBACK_SHALLOW",
                    "TR_ENTRY_HIGHER_HIGH",
                ]
            )

        exit_by_regime = str(row["regime"]) != "TREND"
        exit_by_trend_weaken = _f(row["trend_efficiency"]) < cfg.trend_efficiency_exit_threshold
        exit = exit_by_regime or exit_by_trend_weaken or high_vol
        if exit_by_regime:
            reasons.append("TR_EXIT_REGIME_CHANGED")
        if exit_by_trend_weaken:
            reasons.append("TR_EXIT_TREND_WEAKENED")

        # add signal (pyramid) only when already in position and in profit
        unrealized_pnl = _f(row.get("unrealized_pnl_pct", 0.0))
        can_add = in_position and (unrealized_pnl > 0.0) and (current_add_count < cfg.max_add_count)
        add = gate_ok and can_add and breakout_ok and momentum_ok
        if add:
            reasons.append("TR_ADD_IN_PROFIT")

        if entry:
            in_position = True
            current_add_count = 0
        if add:
            current_add_count += 1
        if exit:
            in_position = False
            current_add_count = 0

        if not reasons:
            reasons.append("TR_EXIT_REGIME_CHANGED")

        entry_signal.append(bool(entry))
        exit_signal.append(bool(exit))
        add_signal.append(bool(add))
        risk_blocked.append(blocked)
        reason_codes.append(sorted(set(reasons)))
        position_size_ratio.append(cfg.default_position_size_ratio if entry else 0.0)

    out = merged[["symbol", "timeframe", "timestamp"]].copy()
    out["entry_signal"] = entry_signal
    out["exit_signal"] = exit_signal
    out["add_signal"] = add_signal
    out["signal_reason_codes"] = reason_codes
    out["risk_blocked"] = risk_blocked
    out["position_size_ratio"] = position_size_ratio
    out["generated_at"] = datetime.now(UTC)
    return out


def _merge_inputs(
    features_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    risk_df: pd.DataFrame | None,
    pnl_df: pd.DataFrame | None,
) -> pd.DataFrame:
    f = features_df.copy()
    r = regime_df.copy()
    f["timestamp"] = pd.to_datetime(f["timestamp"], utc=True)
    r["timestamp"] = pd.to_datetime(r["timestamp"], utc=True)
    merged = f.merge(r, on=["symbol", "timeframe", "timestamp"], how="inner")

    if risk_df is not None:
        k = risk_df.copy()
        k["timestamp"] = pd.to_datetime(k["timestamp"], utc=True)
        merged = merged.merge(k, on=["symbol", "timeframe", "timestamp"], how="left")
    if pnl_df is not None:
        p = pnl_df.copy()
        p["timestamp"] = pd.to_datetime(p["timestamp"], utc=True)
        merged = merged.merge(p, on=["symbol", "timeframe", "timestamp"], how="left")

    if "risk_blocked" not in merged.columns:
        merged["risk_blocked"] = False
    if "unrealized_pnl_pct" not in merged.columns:
        merged["unrealized_pnl_pct"] = 0.0
    merged["risk_blocked"] = merged["risk_blocked"].fillna(False).astype(bool)
    merged["unrealized_pnl_pct"] = merged["unrealized_pnl_pct"].fillna(0.0)
    return merged


def _f(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
