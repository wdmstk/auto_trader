from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.strategy.store import SignalParquetStore
from auto_trader.strategy.trend_strategy import TrendStrategyConfig, generate_trend_signals


def build_and_save_trend_signals(
    *,
    features_path: str | Path,
    regime_path: str | Path,
    symbol: str,
    timeframe: str,
    output_dir: str | Path,
    risk_path: str | Path | None = None,
    pnl_path: str | Path | None = None,
    config: TrendStrategyConfig | None = None,
) -> tuple[pd.DataFrame, str]:
    features = pd.read_parquet(features_path)
    regime = pd.read_parquet(regime_path)
    risk = pd.read_parquet(risk_path) if risk_path else None
    pnl = pd.read_parquet(pnl_path) if pnl_path else None
    signals = generate_trend_signals(
        features_df=features,
        regime_df=regime,
        risk_df=risk,
        pnl_df=pnl,
        config=config,
    )
    store = SignalParquetStore(output_dir, strategy="trend")
    saved = store.save(symbol, timeframe, signals)
    return signals, str(saved)
