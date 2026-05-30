from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import pandas as pd

Regime = Literal["RANGE", "TREND", "HIGH_VOL"]


@dataclass(frozen=True)
class RegimeConfig:
    high_vol_atr_zscore_threshold: float = 3.0
    high_vol_return_abs_zscore_threshold: float = 3.0
    trend_adx_threshold: float = 25.0
    trend_breakout_persistence_min_bars: int = 3
    range_bb_width_percentile_max: float = 40.0
    range_adx_max: float = 20.0
    min_regime_hold_bars: int = 3
    high_vol_cooldown_bars: int = 5


ALLOWED_REASON_CODES = {
    "HV_ATR_SPIKE",
    "HV_RETURN_SPIKE",
    "HV_SPREAD_WIDENING",
    "TR_BREAKOUT_PERSIST",
    "TR_MOMENTUM_PERSIST",
    "TR_ADX_STRONG",
    "RG_LOW_VOL",
    "RG_MEAN_REVERSION_BIAS",
    "RG_FAKE_BREAKOUT_BIAS",
    "FALLBACK_INSUFFICIENT_DATA",
    "FALLBACK_TIMEOUT",
}


def classify_regime(features_df: pd.DataFrame, config: RegimeConfig | None = None) -> pd.DataFrame:
    cfg = config or RegimeConfig()
    required = {
        "symbol",
        "timeframe",
        "timestamp",
        "atr",
        "bb_width",
        "mean_reversion_distance",
        "momentum_persistence",
        "breakout_persistence",
        "trend_efficiency",
        "is_warmup",
    }
    missing = required.difference(features_df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    df = features_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timeframe", "timestamp"]).reset_index(drop=True)
    out_groups: list[pd.DataFrame] = []
    for (_, _), g in df.groupby(["symbol", "timeframe"], sort=False):
        out_groups.append(_classify_group(g.reset_index(drop=True), cfg))
    out = pd.concat(out_groups, ignore_index=True)
    return out


def _classify_group(g: pd.DataFrame, cfg: RegimeConfig) -> pd.DataFrame:
    result = g[["symbol", "timeframe", "timestamp"]].copy()
    result["regime"] = "RANGE"
    result["confidence"] = 0.0
    result["volatility_state"] = "normal"
    result["reason_codes"] = [[] for _ in range(len(g))]
    result["is_trade_allowed"] = False
    result["generated_at"] = datetime.now(UTC)

    atr_mean = g["atr"].rolling(50, min_periods=10).mean()
    atr_std = g["atr"].rolling(50, min_periods=10).std(ddof=0)
    atr_z = (g["atr"] - atr_mean) / atr_std.replace(0.0, pd.NA)

    ret_abs = g["trend_efficiency"].abs()
    ret_mean = ret_abs.rolling(50, min_periods=10).mean()
    ret_std = ret_abs.rolling(50, min_periods=10).std(ddof=0)
    ret_z = (ret_abs - ret_mean) / ret_std.replace(0.0, pd.NA)

    bb_width_rank = g["bb_width"].rank(pct=True) * 100.0
    adx_proxy = (g["trend_efficiency"].abs() * 100.0).clip(0, 50)

    high_vol_mask = (atr_z >= cfg.high_vol_atr_zscore_threshold) | (
        ret_z >= cfg.high_vol_return_abs_zscore_threshold
    )
    trend_mask = (
        (g["breakout_persistence"] >= 0.6)
        & (g["momentum_persistence"] >= 0.5)
        & (adx_proxy >= cfg.trend_adx_threshold)
    )
    range_mask = (bb_width_rank <= cfg.range_bb_width_percentile_max) & (
        adx_proxy <= cfg.range_adx_max
    )

    active_regime: Regime = "RANGE"
    hold_count = 0
    hv_cooldown = 0
    regimes: list[Regime] = []
    confidences: list[float] = []
    vol_states: list[str] = []
    reasons: list[list[str]] = []
    allow: list[bool] = []

    for i in range(len(g)):
        reason_codes: list[str] = []
        if bool(g.loc[i, "is_warmup"]):
            regimes.append("HIGH_VOL")
            confidences.append(0.0)
            vol_states.append("extreme")
            reasons.append(["FALLBACK_INSUFFICIENT_DATA"])
            allow.append(False)
            continue

        desired: Regime = "RANGE"
        atr_i = _safe_float(atr_z.iloc[i])
        ret_i = _safe_float(ret_z.iloc[i])
        if bool(high_vol_mask.iloc[i]):
            desired = "HIGH_VOL"
            if atr_i >= cfg.high_vol_atr_zscore_threshold:
                reason_codes.append("HV_ATR_SPIKE")
            if ret_i >= cfg.high_vol_return_abs_zscore_threshold:
                reason_codes.append("HV_RETURN_SPIKE")
        elif bool(trend_mask.iloc[i]):
            desired = "TREND"
            reason_codes.extend(["TR_BREAKOUT_PERSIST", "TR_MOMENTUM_PERSIST", "TR_ADX_STRONG"])
        elif bool(range_mask.iloc[i]):
            desired = "RANGE"
            reason_codes.extend(["RG_LOW_VOL", "RG_MEAN_REVERSION_BIAS", "RG_FAKE_BREAKOUT_BIAS"])
        else:
            desired = active_regime

        if desired == "HIGH_VOL":
            active_regime = "HIGH_VOL"
            hv_cooldown = cfg.high_vol_cooldown_bars
            hold_count = 0
        elif active_regime == "HIGH_VOL" and hv_cooldown > 0:
            desired = "HIGH_VOL"
            hv_cooldown -= 1
        elif desired != active_regime:
            if hold_count < cfg.min_regime_hold_bars:
                desired = active_regime
                hold_count += 1
            else:
                active_regime = desired
                hold_count = 0
        else:
            hold_count += 1

        regime: Regime = active_regime
        regimes.append(regime)
        confidence = _confidence_for_regime(
            regime,
            atr_i,
            ret_i,
            g.iloc[i],
            _safe_float(bb_width_rank.iloc[i]),
        )
        confidences.append(float(max(0.0, min(1.0, confidence))))
        vol_states.append(_vol_state(atr_i, ret_i))
        if not reason_codes:
            reason_codes = ["FALLBACK_TIMEOUT"]
        reason_codes = [r for r in reason_codes if r in ALLOWED_REASON_CODES]
        reasons.append(reason_codes)
        allow.append(regime != "HIGH_VOL")

    result["regime"] = regimes
    result["confidence"] = confidences
    result["volatility_state"] = vol_states
    result["reason_codes"] = reasons
    result["is_trade_allowed"] = allow
    return result


def _vol_state(atr_z: float, ret_z: float) -> str:
    z = max(_safe_float(atr_z), _safe_float(ret_z))
    if z >= 3.0:
        return "extreme"
    if z >= 1.5:
        return "elevated"
    return "normal"


def _confidence_for_regime(
    regime: Regime,
    atr_z: float,
    ret_z: float,
    row: pd.Series,
    bb_width_pct: float,
) -> float:
    if regime == "HIGH_VOL":
        return min(1.0, max(_safe_float(atr_z), _safe_float(ret_z)) / 5.0)
    if regime == "TREND":
        score = (
            _safe_float(row.get("breakout_persistence", 0.0))
            + _safe_float(row.get("momentum_persistence", 0.0))
            + min(1.0, _safe_float(row.get("trend_efficiency", 0.0)) * 2.0)
        ) / 3.0
        return score
    # RANGE
    width_score = max(0.0, 1.0 - (_safe_float(bb_width_pct) / 100.0))
    mean_rev = min(1.0, abs(_safe_float(row.get("mean_reversion_distance", 0.0))) / 2.0)
    return (width_score + mean_rev) / 2.0


def _safe_float(value: object) -> float:
    try:
        x = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if pd.isna(x):
        return 0.0
    return x
