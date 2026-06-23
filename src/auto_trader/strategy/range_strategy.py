from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from auto_trader.strategy.merge import merge_strategy_inputs


@dataclass(frozen=True)
class RangeStrategyConfig:
    rsi_min: float = 35.0
    rsi_max: float = 55.0
    wick_ratio_min: float = 0.3
    mean_reversion_distance_max: float = -0.3
    exit_mean_reversion_neutral_abs: float = 0.15
    default_position_size_ratio: float = 0.1
    require_reversal_candle: bool = False
    min_entry_score: float = 0.6
    reentry_cooldown_bars: int = 0
    max_hold_bars: int = 16
    enabled_symbols: tuple[str, ...] = ()
    bb_position_max: float = 0.35
    volume_spike_threshold: float = 1.3
    price_vs_recent_low_max: float = 1.5
    w_rsi: float = 1.0
    w_wick: float = 1.0
    w_mr: float = 1.5
    w_bb_pos: float = 2.0
    w_vol: float = 1.0
    w_reversal_bonus: float = 0.5
    exit_atr_trail_multiplier: float = 2.0


def generate_range_signals(
    *,
    features_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    risk_df: pd.DataFrame | None = None,
    config: RangeStrategyConfig | None = None,
) -> pd.DataFrame:
    cfg = config or RangeStrategyConfig()
    merged = merge_strategy_inputs(features_df, regime_df, risk_df)
    merged = merged.sort_values(["symbol", "timeframe", "timestamp"]).reset_index(drop=True)

    n_rows = len(merged)
    symbol_values = merged["symbol"].astype(str).to_numpy(copy=False)
    timeframe_values = merged["timeframe"].astype(str).to_numpy(copy=False)
    regime_values = merged["regime"].astype(str).to_numpy(copy=False)
    trade_allowed_values = merged["is_trade_allowed"].fillna(False).astype(bool).to_numpy(copy=False)
    risk_blocked_values = merged["risk_blocked"].fillna(False).astype(bool).to_numpy(copy=False)
    rsi_values = merged["rsi"].astype(float).to_numpy(copy=False)
    wick_values = merged["wick_ratio"].astype(float).to_numpy(copy=False)
    mr_values = merged["mean_reversion_distance"].astype(float).to_numpy(copy=False)
    reversal_values = merged["reversal_candle_flag"].fillna(0).astype(int).to_numpy(copy=False)

    bb_pos_col = "bb_position" if "bb_position" in merged.columns else None
    bb_pos_values = merged["bb_position"].astype(float).to_numpy(copy=False) if bb_pos_col else None
    vol_spike_col = "volume_spike" if "volume_spike" in merged.columns else None
    vol_spike_values = merged["volume_spike"].fillna(0).astype(int).to_numpy(copy=False) if vol_spike_col else None
    price_low_col = "price_vs_recent_low" if "price_vs_recent_low" in merged.columns else None
    price_low_values = merged["price_vs_recent_low"].astype(float).to_numpy(copy=False) if price_low_col else None
    atr_col = "atr" if "atr" in merged.columns else None
    atr_values = merged["atr"].astype(float).to_numpy(copy=False) if atr_col else None

    enabled_symbols = set(cfg.enabled_symbols)

    entry_signal: list[bool] = []
    exit_signal: list[bool] = []
    risk_blocked: list[bool] = []
    regimes: list[str] = []
    pass_filters: list[bool] = []
    reason_codes: list[list[str]] = []
    size_ratio: list[float] = []

    cooldown_left: dict[tuple[str, str], int] = {}
    hold_bars: dict[tuple[str, str], int] = {}
    in_position_state: dict[tuple[str, str], bool] = {}
    trail_high: dict[tuple[str, str], float] = {}

    total_weight = cfg.w_rsi + cfg.w_wick + cfg.w_mr + cfg.w_bb_pos + cfg.w_vol + cfg.w_reversal_bonus

    for i in range(n_rows):
        reasons: list[str] = []
        blocked = bool(risk_blocked_values[i])
        symbol = str(symbol_values[i])
        timeframe = str(timeframe_values[i])
        key = (symbol, timeframe)
        cd = int(cooldown_left.get(key, 0))
        in_position = bool(in_position_state.get(key, False))
        held_bars = int(hold_bars.get(key, 0))
        symbol_enabled = (not enabled_symbols) or (symbol in enabled_symbols)

        regime = str(regime_values[i])
        is_trade_allowed = bool(trade_allowed_values[i])
        is_high_vol = regime in {"HIGH_VOL", "SUSTAINED"} or not is_trade_allowed
        if is_high_vol:
            reasons.append("RG_BLOCK_HIGH_VOL")
        if blocked:
            reasons.append("RG_BLOCK_RISK_LIMIT")
        if not symbol_enabled:
            reasons.append("RG_BLOCK_SYMBOL_DISABLED")
        if cd > 0:
            reasons.append("RG_BLOCK_REENTRY_COOLDOWN")

        allow_entry_gate = (regime == "RANGE") and is_trade_allowed and (not blocked)

        rsi_ok = cfg.rsi_min <= float(rsi_values[i]) <= cfg.rsi_max
        wick_ok = float(wick_values[i]) >= cfg.wick_ratio_min
        mr_ok = float(mr_values[i]) <= cfg.mean_reversion_distance_max
        rev_ok = int(reversal_values[i]) == 1

        bb_pos_ok = True
        if bb_pos_values is not None:
            bb_pos_ok = float(bb_pos_values[i]) <= cfg.bb_position_max
        vol_ok = False
        if vol_spike_values is not None:
            vol_ok = int(vol_spike_values[i]) == 1
        price_low_ok = True
        if price_low_values is not None:
            price_low_ok = float(price_low_values[i]) <= cfg.price_vs_recent_low_max

        score = (
            cfg.w_rsi * int(rsi_ok)
            + cfg.w_wick * int(wick_ok)
            + cfg.w_mr * int(mr_ok)
            + cfg.w_bb_pos * int(bb_pos_ok)
            + cfg.w_vol * int(vol_ok)
            + cfg.w_reversal_bonus * int(rev_ok)
        ) / total_weight
        score_ok = score >= cfg.min_entry_score

        entry = allow_entry_gate and symbol_enabled and (not in_position) and (cd <= 0) and score_ok and price_low_ok
        if entry:
            entry_reasons = ["RG_ENTRY_SCORE_OK"]
            if rsi_ok:
                entry_reasons.append("RG_ENTRY_RSI_REBOUND")
            if wick_ok:
                entry_reasons.append("RG_ENTRY_WICK_CONFIRM")
            if rev_ok:
                entry_reasons.append("RG_ENTRY_REVERSAL_CANDLE")
            if bb_pos_ok:
                entry_reasons.append("RG_ENTRY_BB_LOWER_ZONE")
            if vol_ok:
                entry_reasons.append("RG_ENTRY_VOLUME_SPIKE")
            reasons.extend(entry_reasons)
        elif allow_entry_gate and symbol_enabled and (not in_position) and (cd <= 0) and (not score_ok):
            reasons.append("RG_BLOCK_SCORE_LOW")

        exit_mr = abs(float(mr_values[i])) <= cfg.exit_mean_reversion_neutral_abs
        exit_regime = regime not in {"RANGE", "SPIKE"}
        exit_max_hold = cfg.max_hold_bars > 0 and in_position and held_bars >= cfg.max_hold_bars

        exit_atr_trail = False
        if in_position and atr_values is not None and cfg.exit_atr_trail_multiplier > 0:
            current_trail = float(trail_high.get(key, 0.0))
            current_close = float(mr_values[i])
            if current_close > current_trail:
                trail_high[key] = current_close
                current_trail = current_close
            trail_stop = current_trail - cfg.exit_atr_trail_multiplier * float(atr_values[i])
            if current_close <= trail_stop and held_bars > 1:
                exit_atr_trail = True

        exit_sig = exit_mr or exit_regime or exit_max_hold or exit_atr_trail
        if exit_mr:
            reasons.append("RG_EXIT_MEAN_REVERTED")
        if exit_regime:
            reasons.append("RG_EXIT_REGIME_CHANGED")
        if exit_max_hold:
            reasons.append("RG_EXIT_MAX_HOLD")
        if exit_atr_trail:
            reasons.append("RG_EXIT_ATR_TRAIL")

        if not reasons:
            reasons.append("RG_EXIT_REGIME_CHANGED")

        if entry and cfg.reentry_cooldown_bars > 0:
            cooldown_left[key] = int(cfg.reentry_cooldown_bars)
        elif cd > 0:
            cooldown_left[key] = cd - 1

        if entry:
            in_position_state[key] = True
            hold_bars[key] = 0
            trail_high[key] = float(mr_values[i])
        elif in_position and not exit_sig:
            in_position_state[key] = True
            hold_bars[key] = held_bars + 1
        else:
            in_position_state[key] = False
            hold_bars[key] = 0
            trail_high.pop(key, None)

        entry_signal.append(bool(entry))
        exit_signal.append(bool(exit_sig))
        risk_blocked.append(blocked)
        regimes.append(regime)
        pass_filters.append(bool(allow_entry_gate))
        reason_codes.append(sorted(set(reasons)))
        size_ratio.append(cfg.default_position_size_ratio if entry else 0.0)

    out = merged[["symbol", "timeframe", "timestamp"]].copy()
    out["regime"] = regimes
    out["pass_filter"] = pass_filters
    out["entry_signal"] = entry_signal
    out["exit_signal"] = exit_signal
    out["signal_reason_codes"] = reason_codes
    out["risk_blocked"] = risk_blocked
    out["position_size_ratio"] = size_ratio
    out["generated_at"] = datetime.now(UTC)
    return out
