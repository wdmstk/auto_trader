from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.features.engine import FeatureConfig, compute_features
from auto_trader.features.store import FeatureParquetStore


def generate_and_save_features(
    *,
    ohlcv_path: str | Path,
    symbol: str,
    timeframe: str,
    output_dir: str | Path,
    config: FeatureConfig | None = None,
) -> tuple[pd.DataFrame, str]:
    df = pd.read_parquet(ohlcv_path)
    features = compute_features(df, config=config)
    store = FeatureParquetStore(output_dir)
    saved_path = store.save(symbol, timeframe, features)
    return features, str(saved_path)
