from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.regime.classifier import RegimeConfig, classify_regime
from auto_trader.regime.store import RegimeParquetStore


def classify_and_save_regime(
    *,
    feature_path: str | Path,
    symbol: str,
    timeframe: str,
    output_dir: str | Path,
    config: RegimeConfig | None = None,
) -> tuple[pd.DataFrame, str]:
    features = pd.read_parquet(feature_path)
    regime_df = classify_regime(features, config=config)
    store = RegimeParquetStore(output_dir)
    saved_path = store.save(symbol, timeframe, regime_df)
    return regime_df, str(saved_path)
