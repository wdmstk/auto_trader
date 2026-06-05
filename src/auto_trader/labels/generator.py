from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd


@dataclass(frozen=True)
class LabelConfig:
    tp_pct: float = 0.04
    sl_pct: float = 0.02
    max_horizon_bars: int = 120
    label_version: str = "v1"


def validate_timestamp_integrity(df: pd.DataFrame) -> None:
    required = {"symbol", "timeframe", "timestamp"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    work = df.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    for (_, _), g in work.groupby(["symbol", "timeframe"], sort=False):
        if not g["timestamp"].is_monotonic_increasing:
            raise ValueError("timestamp must be strictly non-decreasing per symbol/timeframe")
        if g["timestamp"].duplicated().any():
            raise ValueError("duplicate timestamp detected per symbol/timeframe")


def validate_no_leakage(features_df: pd.DataFrame, labels_df: pd.DataFrame) -> None:
    # Label timestamp must match feature timestamp only; no future alignment allowed.
    fk = features_df[["symbol", "timeframe", "timestamp"]].copy()
    lk = labels_df[["symbol", "timeframe", "timestamp"]].copy()
    fk["timestamp"] = pd.to_datetime(fk["timestamp"], utc=True)
    lk["timestamp"] = pd.to_datetime(lk["timestamp"], utc=True)

    merged = lk.merge(fk, on=["symbol", "timeframe", "timestamp"], how="left", indicator=True)
    if (merged["_merge"] != "both").any():
        raise ValueError("label rows must align to existing feature timestamps")


def generate_tp_sl_labels(
    ohlcv_df: pd.DataFrame,
    config: LabelConfig | None = None,
) -> pd.DataFrame:
    cfg = config or LabelConfig()
    required = {"symbol", "timeframe", "timestamp", "close", "high", "low"}
    missing = required.difference(ohlcv_df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    df = ohlcv_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timeframe", "timestamp"]).reset_index(drop=True)
    validate_timestamp_integrity(df)

    all_out: list[pd.DataFrame] = []
    for (_, _), g in df.groupby(["symbol", "timeframe"], sort=False):
        all_out.append(_label_group(g.reset_index(drop=True), cfg))
    out = pd.concat(all_out, ignore_index=True)
    return out


def _label_group(g: pd.DataFrame, cfg: LabelConfig) -> pd.DataFrame:
    n = len(g)
    close_values = g["close"].astype(float).to_numpy(copy=False)
    high_values = g["high"].astype(float).to_numpy(copy=False)
    low_values = g["low"].astype(float).to_numpy(copy=False)
    labels: list[int | None] = []
    hit_bars: list[int | None] = []
    reasons: list[str] = []

    for i in range(n):
        entry = float(close_values[i])
        tp = entry * (1.0 + cfg.tp_pct)
        sl = entry * (1.0 - cfg.sl_pct)
        label: int | None = None
        hit_bar: int | None = None
        reason = "NO_HIT_IN_HORIZON"

        end = min(n, i + 1 + cfg.max_horizon_bars)
        for j in range(i + 1, end):
            high = float(high_values[j])
            low = float(low_values[j])
            tp_hit = high >= tp
            sl_hit = low <= sl
            if tp_hit and sl_hit:
                # Conservative side: treat same-bar dual touch as SL-first.
                label = 0
                hit_bar = j - i
                reason = "BOTH_HIT_SAME_BAR_SL_PRIORITIZED"
                break
            if tp_hit:
                label = 1
                hit_bar = j - i
                reason = "TP_FIRST"
                break
            if sl_hit:
                label = 0
                hit_bar = j - i
                reason = "SL_FIRST"
                break

        labels.append(label)
        hit_bars.append(hit_bar)
        reasons.append(reason)

    out = g[["symbol", "timeframe", "timestamp"]].copy()
    out["label"] = labels
    out["hit_bars"] = hit_bars
    out["tp_pct"] = cfg.tp_pct
    out["sl_pct"] = cfg.sl_pct
    out["max_horizon_bars"] = cfg.max_horizon_bars
    out["label_reason"] = reasons
    out["label_version"] = cfg.label_version
    out["generated_at"] = datetime.now(UTC)
    return out


def _safe_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
