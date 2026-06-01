from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.strategy.range_strategy import RangeStrategyConfig, generate_range_signals
from auto_trader.strategy.store import SignalParquetStore


def build_and_save_range_signals(
    *,
    features_path: str | Path,
    regime_path: str | Path,
    symbol: str,
    timeframe: str,
    output_dir: str | Path,
    risk_path: str | Path | None = None,
    config: RangeStrategyConfig | None = None,
) -> tuple[pd.DataFrame, str]:
    features = pd.read_parquet(features_path)
    regime = pd.read_parquet(regime_path)
    risk = pd.read_parquet(risk_path) if risk_path else None
    signals = generate_range_signals(
        features_df=features,
        regime_df=regime,
        risk_df=risk,
        config=config,
    )
    store = SignalParquetStore(output_dir, strategy="range")
    saved = store.save(symbol, timeframe, signals)
    return signals, str(saved)
