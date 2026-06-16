from __future__ import annotations

import pandas as pd


def _series_or_default(df: pd.DataFrame, col: str, default: object) -> pd.Series:
    if col in df.columns:
        return df[col]
    return pd.Series([default] * len(df), index=df.index)


def build_regime_segments(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "regime"}
    if frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame(columns=["start", "end", "regime"])

    work = frame[["timestamp", "regime"]].copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    work["regime"] = work["regime"].fillna("UNKNOWN").astype(str)
    work = work.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    if work.empty:
        return pd.DataFrame(columns=["start", "end", "regime"])

    work["regime_group"] = work["regime"].ne(work["regime"].shift()).cumsum()
    segments = (
        work.groupby("regime_group", as_index=False)
        .agg(start=("timestamp", "min"), end=("timestamp", "max"), regime=("regime", "first"))
        .drop(columns=["regime_group"], errors="ignore")
    )
    if len(work) > 1:
        diffs = work["timestamp"].diff().dropna()
        step = pd.Timedelta(diffs.median()) if not diffs.empty else pd.Timedelta(minutes=1)
    else:
        step = pd.Timedelta(minutes=1)
    segments["end"] = pd.to_datetime(segments["end"], utc=True) + step
    return segments[["start", "end", "regime"]]


def build_overlay_frame(
    *,
    ohlcv_df: pd.DataFrame,
    signal_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    risk_df: pd.DataFrame,
    max_rows: int = 500,
) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    if ohlcv_df.empty or not required.issubset(ohlcv_df.columns):
        return pd.DataFrame()

    base = ohlcv_df[["timestamp", "open", "high", "low", "close"]].copy()
    base["timestamp"] = pd.to_datetime(base["timestamp"], utc=True)
    base = base.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    if max_rows > 0 and len(base) > max_rows:
        base = base.tail(max_rows).copy()
    if base.empty:
        return pd.DataFrame()
    window_start = base["timestamp"].iloc[0]
    window_end = base["timestamp"].iloc[-1]

    has_ml_score = False
    if not signal_df.empty and "timestamp" in signal_df.columns:
        s = signal_df.copy()
        s["timestamp"] = pd.to_datetime(s["timestamp"], utc=True)
        s = s[(s["timestamp"] >= window_start) & (s["timestamp"] <= window_end)]
        keep = ["timestamp"]
        if "entry_signal" in s.columns:
            keep.append("entry_signal")
        if "exit_signal" in s.columns:
            keep.append("exit_signal")
        if "ml_score" in s.columns:
            keep.append("ml_score")
            has_ml_score = True
        if "position_size_ratio" in s.columns:
            keep.append("position_size_ratio")
        base = base.merge(s[keep], on="timestamp", how="left")

    if not regime_df.empty and "timestamp" in regime_df.columns and "regime" in regime_df.columns:
        r = regime_df[["timestamp", "regime"]].copy()
        r["timestamp"] = pd.to_datetime(r["timestamp"], utc=True)
        r = r[(r["timestamp"] >= window_start) & (r["timestamp"] <= window_end)]
        base = base.merge(r, on="timestamp", how="left")

    if not risk_df.empty and "timestamp" in risk_df.columns:
        k = risk_df.copy()
        k["timestamp"] = pd.to_datetime(k["timestamp"], utc=True)
        k = k[(k["timestamp"] >= window_start) & (k["timestamp"] <= window_end)]
        if "risk_blocked" in k.columns:
            base = base.merge(k[["timestamp", "risk_blocked"]], on="timestamp", how="left")

    base["entry_signal"] = _series_or_default(base, "entry_signal", False).astype(bool)
    base["exit_signal"] = _series_or_default(base, "exit_signal", False).astype(bool)
    ml_score = pd.to_numeric(
        _series_or_default(base, "ml_score", 0.0),
        errors="coerce",
    ).fillna(0.0)
    if not has_ml_score or float(ml_score.abs().sum()) == 0.0:
        proxy = pd.to_numeric(
            _series_or_default(base, "position_size_ratio", 0.0),
            errors="coerce",
        ).fillna(0.0)
        ml_score = proxy
    base["ml_score"] = ml_score
    base["ml_score_source"] = "ml_score" if has_ml_score else "position_size_ratio"
    base["risk_blocked"] = _series_or_default(base, "risk_blocked", False).astype(bool)
    base["regime"] = _series_or_default(base, "regime", "UNKNOWN").astype(str)

    # Sparse markers for entry/exit overlay on top of close line.
    base["entry_marker"] = base["close"].where(base["entry_signal"])
    base["exit_marker"] = base["close"].where(base["exit_signal"])
    base["risk_block_marker"] = base["close"].where(base["risk_blocked"])

    # Regime as numeric band for quick visual inspection.
    mapping = {"RANGE": 1.0, "TREND": 2.0, "SPIKE": 3.0, "SUSTAINED": 4.0, "HIGH_VOL": 4.0}
    base["regime_band"] = base["regime"].map(mapping).fillna(0.0)

    out = base.sort_values("timestamp").reset_index(drop=True)
    return out
