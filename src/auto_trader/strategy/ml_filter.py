from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from auto_trader.ml.model import apply_model_artifacts, load_model_artifacts


def apply_signal_ml_filter(
    *,
    features_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    signals_df: pd.DataFrame,
    artifact_path: str | Path,
) -> pd.DataFrame:
    artifacts = load_model_artifacts(artifact_path)
    regime_cols = [
        "symbol",
        "timeframe",
        "timestamp",
        *[col for col in ["confidence", "is_trade_allowed", "regime"] if col in regime_df.columns],
    ]
    feat = features_df.merge(
        regime_df[regime_cols],
        on=["symbol", "timeframe", "timestamp"],
        how="left",
        validate="one_to_one",
        suffixes=("", "_regime"),
    )
    merged = signals_df.merge(
        feat[["symbol", "timeframe", "timestamp", "feature_version", *artifacts.feature_columns]],
        on=["symbol", "timeframe", "timestamp"],
        how="left",
        validate="one_to_one",
        suffixes=("", "_feature"),
    )
    scored = apply_model_artifacts(dataset=merged, artifacts=artifacts)
    scored["ml_score_source"] = "ml_score"
    keep_cols = list(signals_df.columns)
    extra_cols = [
        "ml_score",
        "ml_score_source",
        "ml_threshold",
        "ml_pass_filter",
        "ml_model_version",
        "ml_feature_version",
        "ml_train_start",
        "ml_train_end",
    ]
    return scored[keep_cols + extra_cols].copy()


def resolve_ml_artifact_path(artifact_path: str | Path | None = None) -> Path | None:
    if artifact_path is not None:
        path = Path(artifact_path)
        if path.exists():
            return path

    env_path = os.getenv("ML_ARTIFACT_PATH", "").strip()
    if env_path:
        path = Path(env_path)
        if path.exists():
            return path

    default_path = Path("data/ml/artifacts/latest")
    if default_path.exists():
        return default_path

    default_meta = default_path / "metadata.json"
    if default_meta.exists():
        return default_path

    return None
