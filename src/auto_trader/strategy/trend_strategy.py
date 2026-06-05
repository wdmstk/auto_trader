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
    min_entry_score: float = 1.0
    reentry_cooldown_bars: int = 0
    enabled_symbols: tuple[str, ...] = ()


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

    n_rows = len(merged)
    symbol_values = merged["symbol"].astype(str).to_numpy(copy=False)
    timeframe_values = merged["timeframe"].astype(str).to_numpy(copy=False)
    regime_values = merged["regime"].astype(str).to_numpy(copy=False)
    trade_allowed_values = (
        merged["is_trade_allowed"].fillna(False).astype(bool).to_numpy(copy=False)
    )
    risk_blocked_values = merged["risk_blocked"].fillna(False).astype(bool).to_numpy(copy=False)
    breakout_values = merged["breakout_persistence"].astype(float).to_numpy(copy=False)
    momentum_values = merged["momentum_persistence"].astype(float).to_numpy(copy=False)
    pullback_values = merged["pullback_shallowness"].astype(float).to_numpy(copy=False)
    higher_high_values = merged["higher_high_persistence"].astype(float).to_numpy(copy=False)
    trend_efficiency_values = merged["trend_efficiency"].astype(float).to_numpy(copy=False)
    unrealized_values = merged["unrealized_pnl_pct"].astype(float).to_numpy(copy=False)
    enabled_symbols = set(cfg.enabled_symbols)

    entry_signal: list[bool] = []
    exit_signal: list[bool] = []
    add_signal: list[bool] = []
    risk_blocked: list[bool] = []
    regimes: list[str] = []
    pass_filters: list[bool] = []
    reason_codes: list[list[str]] = []
    position_size_ratio: list[float] = []

    state: dict[tuple[str, str], dict[str, int | bool]] = {}

    for i in range(n_rows):
        reasons: list[str] = []
        blocked = bool(risk_blocked_values[i])
        regime = str(regime_values[i])
        is_trade_allowed = bool(trade_allowed_values[i])
        high_vol = (regime == "HIGH_VOL") or (not is_trade_allowed)
        symbol = str(symbol_values[i])
        timeframe = str(timeframe_values[i])
        key = (symbol, timeframe)
        st = state.setdefault(key, {"in_position": False, "add_count": 0, "cooldown": 0})
        in_position = bool(st["in_position"])
        current_add_count = int(st["add_count"])
        cooldown = int(st["cooldown"])
        symbol_enabled = (not enabled_symbols) or (symbol in enabled_symbols)

        if high_vol:
            reasons.append("TR_BLOCK_HIGH_VOL")
        if blocked:
            reasons.append("TR_BLOCK_RISK_LIMIT")
        if not symbol_enabled:
            reasons.append("TR_BLOCK_SYMBOL_DISABLED")
        if cooldown > 0:
            reasons.append("TR_BLOCK_REENTRY_COOLDOWN")

        regime_ok = regime == "TREND" and is_trade_allowed
        gate_ok = regime_ok and (not high_vol) and (not blocked)

        breakout_ok = float(breakout_values[i]) >= cfg.breakout_persistence_min
        momentum_ok = float(momentum_values[i]) >= cfg.momentum_persistence_min
        pullback_ok = float(pullback_values[i]) >= cfg.pullback_shallowness_min
        higher_high_ok = float(higher_high_values[i]) >= cfg.higher_high_persistence_min
        score = (int(breakout_ok) + int(momentum_ok) + int(pullback_ok) + int(higher_high_ok)) / 4.0
        score_ok = score >= cfg.min_entry_score

        entry = (
            gate_ok
            and symbol_enabled
            and (cooldown <= 0)
            and score_ok
            and breakout_ok
            and momentum_ok
            and pullback_ok
            and higher_high_ok
        )
        if entry:
            reasons.extend(
                [
                    "TR_ENTRY_SCORE_OK",
                    "TR_ENTRY_BREAKOUT_PERSIST",
                    "TR_ENTRY_MOMENTUM_PERSIST",
                    "TR_ENTRY_PULLBACK_SHALLOW",
                    "TR_ENTRY_HIGHER_HIGH",
                ]
            )
        elif gate_ok and symbol_enabled and (cooldown <= 0) and (not score_ok):
            reasons.append("TR_BLOCK_SCORE_LOW")

        exit_by_regime = regime != "TREND"
        exit_by_trend_weaken = (
            float(trend_efficiency_values[i]) < cfg.trend_efficiency_exit_threshold
        )
        exit = exit_by_regime or exit_by_trend_weaken or high_vol
        if exit_by_regime:
            reasons.append("TR_EXIT_REGIME_CHANGED")
        if exit_by_trend_weaken:
            reasons.append("TR_EXIT_TREND_WEAKENED")

        # add signal (pyramid) only when already in position and in profit
        unrealized_pnl = float(unrealized_values[i])
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

        if entry and cfg.reentry_cooldown_bars > 0:
            cooldown = int(cfg.reentry_cooldown_bars)
        elif cooldown > 0:
            cooldown -= 1

        st["in_position"] = in_position
        st["add_count"] = current_add_count
        st["cooldown"] = cooldown

        entry_signal.append(bool(entry))
        exit_signal.append(bool(exit))
        add_signal.append(bool(add))
        risk_blocked.append(blocked)
        regimes.append(regime)
        pass_filters.append(bool(gate_ok))
        reason_codes.append(sorted(set(reasons)))
        position_size_ratio.append(cfg.default_position_size_ratio if entry else 0.0)

    out = merged[["symbol", "timeframe", "timestamp"]].copy()
    out["regime"] = regimes
    out["pass_filter"] = pass_filters
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
        if "timestamp" in k.columns:
            k["timestamp"] = pd.to_datetime(k["timestamp"], utc=True)
            risk_merge_keys = ["symbol", "timestamp"]
            if "timeframe" in k.columns:
                risk_merge_keys = ["symbol", "timeframe", "timestamp"]
            merged = merged.merge(k, on=risk_merge_keys, how="left")
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
