from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd


@dataclass(frozen=True)
class RangeStrategyConfig:
    rsi_min: float = 40.0
    rsi_max: float = 50.0
    wick_ratio_min: float = 0.5
    mean_reversion_distance_max: float = -0.1
    exit_mean_reversion_neutral_abs: float = 0.05
    default_position_size_ratio: float = 0.1
    require_reversal_candle: bool = True
    min_entry_score: float = 1.0
    reentry_cooldown_bars: int = 0
    enabled_symbols: tuple[str, ...] = ()


def generate_range_signals(
    *,
    features_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    risk_df: pd.DataFrame | None = None,
    config: RangeStrategyConfig | None = None,
) -> pd.DataFrame:
    cfg = config or RangeStrategyConfig()
    merged = _merge_inputs(features_df, regime_df, risk_df)
    merged = merged.sort_values(["symbol", "timeframe", "timestamp"]).reset_index(drop=True)

    entry_signal: list[bool] = []
    exit_signal: list[bool] = []
    risk_blocked: list[bool] = []
    regimes: list[str] = []
    pass_filters: list[bool] = []
    reason_codes: list[list[str]] = []
    size_ratio: list[float] = []

    cooldown_left: dict[tuple[str, str], int] = {}
    for _, row in merged.iterrows():
        reasons: list[str] = []
        blocked = bool(row.get("risk_blocked", False))
        symbol = str(row.get("symbol", ""))
        timeframe = str(row.get("timeframe", ""))
        key = (symbol, timeframe)
        cd = int(cooldown_left.get(key, 0))
        symbol_enabled = (not cfg.enabled_symbols) or (symbol in cfg.enabled_symbols)

        is_high_vol = str(row["regime"]) == "HIGH_VOL" or not bool(row["is_trade_allowed"])
        if is_high_vol:
            reasons.append("RG_BLOCK_HIGH_VOL")
        if blocked:
            reasons.append("RG_BLOCK_RISK_LIMIT")
        if not symbol_enabled:
            reasons.append("RG_BLOCK_SYMBOL_DISABLED")
        if cd > 0:
            reasons.append("RG_BLOCK_REENTRY_COOLDOWN")

        allow_entry_gate = (
            (str(row["regime"]) == "RANGE") and bool(row["is_trade_allowed"]) and (not blocked)
        )

        rsi_ok = cfg.rsi_min <= _f(row["rsi"]) <= cfg.rsi_max
        wick_ok = _f(row["wick_ratio"]) >= cfg.wick_ratio_min
        mr_ok = _f(row["mean_reversion_distance"]) <= cfg.mean_reversion_distance_max
        rev_ok = (int(row["reversal_candle_flag"]) == 1) if cfg.require_reversal_candle else True
        score = (int(rsi_ok) + int(wick_ok) + int(mr_ok) + int(rev_ok)) / 4.0
        score_ok = score >= cfg.min_entry_score

        entry = (
            allow_entry_gate
            and symbol_enabled
            and (cd <= 0)
            and score_ok
            and rsi_ok
            and wick_ok
            and mr_ok
            and rev_ok
        )
        if entry:
            reasons.extend(
                [
                    "RG_ENTRY_SCORE_OK",
                    "RG_ENTRY_RSI_REBOUND",
                    "RG_ENTRY_WICK_CONFIRM",
                    "RG_ENTRY_REVERSAL_CANDLE",
                ]
            )
        elif allow_entry_gate and symbol_enabled and (cd <= 0) and (not score_ok):
            reasons.append("RG_BLOCK_SCORE_LOW")

        exit_mr = abs(_f(row["mean_reversion_distance"])) <= cfg.exit_mean_reversion_neutral_abs
        exit_regime = str(row["regime"]) != "RANGE"
        exit_sig = exit_mr or exit_regime
        if exit_mr:
            reasons.append("RG_EXIT_MEAN_REVERTED")
        if exit_regime:
            reasons.append("RG_EXIT_REGIME_CHANGED")

        if not reasons:
            reasons.append("RG_EXIT_REGIME_CHANGED")

        if entry and cfg.reentry_cooldown_bars > 0:
            cooldown_left[key] = int(cfg.reentry_cooldown_bars)
        elif cd > 0:
            cooldown_left[key] = cd - 1

        entry_signal.append(bool(entry))
        exit_signal.append(bool(exit_sig))
        risk_blocked.append(blocked)
        regimes.append(str(row.get("regime", "")))
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


def _merge_inputs(
    features_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    risk_df: pd.DataFrame | None,
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
    if "risk_blocked" not in merged.columns:
        merged["risk_blocked"] = False
    merged["risk_blocked"] = merged["risk_blocked"].fillna(False).astype(bool)
    return merged


def _f(v: object) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
