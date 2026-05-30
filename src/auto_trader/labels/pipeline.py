from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.labels.generator import (
    LabelConfig,
    generate_tp_sl_labels,
    validate_no_leakage,
)
from auto_trader.labels.store import LabelParquetStore


def generate_and_save_labels(
    *,
    ohlcv_path: str | Path,
    symbol: str,
    timeframe: str,
    output_dir: str | Path,
    config: LabelConfig | None = None,
    features_path: str | Path | None = None,
) -> tuple[pd.DataFrame, str]:
    ohlcv_df = pd.read_parquet(ohlcv_path)
    labels = generate_tp_sl_labels(ohlcv_df, config=config)

    if features_path is not None:
        features_df = pd.read_parquet(features_path)
        validate_no_leakage(features_df, labels)

    store = LabelParquetStore(output_dir)
    saved_path = store.save(symbol, timeframe, labels)
    return labels, str(saved_path)
