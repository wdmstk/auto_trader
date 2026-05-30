from __future__ import annotations

import pandas as pd


def _series_or_default(df: pd.DataFrame, col: str, default: object) -> pd.Series:
    if col in df.columns:
        return df[col]
    return pd.Series([default] * len(df), index=df.index)


def build_overlay_frame(
    *,
    ohlcv_df: pd.DataFrame,
    signal_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    risk_df: pd.DataFrame,
    max_rows: int = 500,
) -> pd.DataFrame:
    if ohlcv_df.empty or "timestamp" not in ohlcv_df.columns or "close" not in ohlcv_df.columns:
        return pd.DataFrame()

    base = ohlcv_df[["timestamp", "close"]].copy()
    base["timestamp"] = pd.to_datetime(base["timestamp"], utc=True)

    if not signal_df.empty and "timestamp" in signal_df.columns:
        s = signal_df.copy()
        s["timestamp"] = pd.to_datetime(s["timestamp"], utc=True)
        keep = ["timestamp"]
        if "entry_signal" in s.columns:
            keep.append("entry_signal")
        if "exit_signal" in s.columns:
            keep.append("exit_signal")
        if "ml_score" in s.columns:
            keep.append("ml_score")
        base = base.merge(s[keep], on="timestamp", how="left")

    if not regime_df.empty and "timestamp" in regime_df.columns and "regime" in regime_df.columns:
        r = regime_df[["timestamp", "regime"]].copy()
        r["timestamp"] = pd.to_datetime(r["timestamp"], utc=True)
        base = base.merge(r, on="timestamp", how="left")

    if not risk_df.empty and "timestamp" in risk_df.columns:
        k = risk_df.copy()
        k["timestamp"] = pd.to_datetime(k["timestamp"], utc=True)
        if "risk_blocked" in k.columns:
            base = base.merge(k[["timestamp", "risk_blocked"]], on="timestamp", how="left")

    base["entry_signal"] = _series_or_default(base, "entry_signal", False).astype(bool)
    base["exit_signal"] = _series_or_default(base, "exit_signal", False).astype(bool)
    ml_score = pd.to_numeric(
        _series_or_default(base, "ml_score", 0.0),
        errors="coerce",
    ).fillna(0.0)
    base["ml_score"] = ml_score
    base["risk_blocked"] = _series_or_default(base, "risk_blocked", False).astype(bool)
    base["regime"] = _series_or_default(base, "regime", "UNKNOWN").astype(str)

    # Sparse markers for entry/exit overlay on top of close line.
    base["entry_marker"] = base["close"].where(base["entry_signal"])
    base["exit_marker"] = base["close"].where(base["exit_signal"])
    base["risk_block_marker"] = base["close"].where(base["risk_blocked"])

    # Regime as numeric band for quick visual inspection.
    mapping = {"RANGE": 1.0, "TREND": 2.0, "HIGH_VOL": 3.0}
    base["regime_band"] = base["regime"].map(mapping).fillna(0.0)

    out = base.sort_values("timestamp").tail(max_rows).reset_index(drop=True)
    return out
