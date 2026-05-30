from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.ml.dataset import DatasetArtifacts, add_timeseries_split, build_dataset
from auto_trader.ml.model import ModelArtifacts, apply_model_filter, train_binary_classifier


def run_ml_pipeline(
    *,
    features_path: str | Path,
    regime_path: str | Path,
    signals_path: str | Path,
    labels_path: str | Path,
) -> tuple[pd.DataFrame, DatasetArtifacts, ModelArtifacts]:
    features = pd.read_parquet(features_path)
    regime = pd.read_parquet(regime_path)
    signals = pd.read_parquet(signals_path)
    labels = pd.read_parquet(labels_path)

    artifacts = build_dataset(
        features_df=features,
        regime_df=regime,
        signals_df=signals,
        labels_df=labels,
    )
    with_split = add_timeseries_split(artifacts.dataset)
    trained = train_binary_classifier(
        dataset=with_split,
        feature_columns=artifacts.feature_columns,
    )
    scored = apply_model_filter(
        model=trained.model,
        threshold=trained.threshold,
        dataset=with_split,
        feature_columns=artifacts.feature_columns,
    )
    return scored, artifacts, trained
