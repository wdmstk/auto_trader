from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

KEY_COLS = ["symbol", "timeframe", "timestamp"]


@dataclass(frozen=True)
class DatasetArtifacts:
    dataset: pd.DataFrame
    feature_columns: list[str]


def build_dataset(
    *,
    features_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    signals_df: pd.DataFrame,
    labels_df: pd.DataFrame,
    feature_columns: Sequence[str] | None = None,
) -> DatasetArtifacts:
    f = _normalize_keys(features_df)
    r = _normalize_keys(regime_df)
    s = _normalize_keys(signals_df)
    labels = _normalize_keys(labels_df)

    _assert_unique_keys(f, "features")
    _assert_unique_keys(r, "regime")
    _assert_unique_keys(s, "signals")
    _assert_unique_keys(labels, "labels")

    merged = f.merge(r, on=KEY_COLS, how="inner", suffixes=("", "_reg"))
    merged = merged.merge(s, on=KEY_COLS, how="inner", suffixes=("", "_sig"))
    merged = merged.merge(labels, on=KEY_COLS, how="inner", suffixes=("", "_lbl"))

    merged = merged.dropna(subset=["label"]).copy()
    merged["label"] = merged["label"].astype(int)

    if feature_columns is None:
        blocked_prefix = (
            "label",
            "generated_at",
            "signal_reason_codes",
            "reason_codes",
            "entry_signal",
            "exit_signal",
            "add_signal",
            "pass_filter",
            "ml_score",
            "threshold",
        )
        auto = [
            c
            for c in merged.columns
            if c not in KEY_COLS
            and merged[c].dtype != "O"
            and not any(c.startswith(p) for p in blocked_prefix)
        ]
        feature_cols = sorted(auto)
    else:
        feature_cols = [c for c in feature_columns if c in merged.columns]

    if not feature_cols:
        raise ValueError("no usable feature columns")

    return DatasetArtifacts(dataset=merged, feature_columns=feature_cols)


def add_timeseries_split(
    df: pd.DataFrame,
    *,
    train_ratio: float = 0.6,
    valid_ratio: float = 0.2,
) -> pd.DataFrame:
    if not 0.0 < train_ratio < 1.0:
        raise ValueError("train_ratio must be in (0,1)")
    if not 0.0 < valid_ratio < 1.0:
        raise ValueError("valid_ratio must be in (0,1)")
    if train_ratio + valid_ratio >= 1.0:
        raise ValueError("train_ratio + valid_ratio must be < 1")

    out = _normalize_keys(df).sort_values(KEY_COLS).reset_index(drop=True).copy()
    n = len(out)
    train_end = int(n * train_ratio)
    valid_end = int(n * (train_ratio + valid_ratio))

    split = pd.Series(["test"] * n)
    split.iloc[:train_end] = "train"
    split.iloc[train_end:valid_end] = "valid"
    out["split"] = split
    return out


def _normalize_keys(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in KEY_COLS:
        if col not in out.columns:
            raise ValueError(f"missing key column: {col}")
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out


def _assert_unique_keys(df: pd.DataFrame, name: str) -> None:
    if df.duplicated(KEY_COLS).any():
        raise ValueError(f"{name} has duplicated keys")
