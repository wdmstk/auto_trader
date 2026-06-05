from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.drift.gate import is_drift_trade_blocked
from auto_trader.strategy.ml_filter import apply_signal_ml_filter
from auto_trader.strategy.range_strategy import RangeStrategyConfig, generate_range_signals
from auto_trader.strategy.session_gate import apply_session_gate
from auto_trader.strategy.store import SignalParquetStore


def build_and_save_range_signals(
    *,
    features_path: str | Path,
    regime_path: str | Path,
    symbol: str,
    timeframe: str,
    output_dir: str | Path,
    risk_path: str | Path | None = None,
    drift_report_path: str | Path | None = None,
    ml_artifact_path: str | Path | None = None,
    allowed_hours: str | None = None,
    config: RangeStrategyConfig | None = None,
) -> tuple[pd.DataFrame, str]:
    features = pd.read_parquet(features_path)
    regime = pd.read_parquet(regime_path)
    if is_drift_trade_blocked(drift_report_path):
        regime = regime.copy()
        regime["is_trade_allowed"] = False
    risk = pd.read_parquet(risk_path) if risk_path else None
    signals = generate_range_signals(
        features_df=features,
        regime_df=regime,
        risk_df=risk,
        config=config,
    )
    if ml_artifact_path is not None:
        signals = _apply_ml_filter(
            features_df=features,
            regime_df=regime,
            signals_df=signals,
            artifact_path=ml_artifact_path,
        )
    if allowed_hours:
        signals = apply_session_gate(signals, allowed_hours=allowed_hours)
    store = SignalParquetStore(output_dir, strategy="range")
    saved = store.save(symbol, timeframe, signals)
    return signals, str(saved)


def _apply_ml_filter(
    *,
    features_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    signals_df: pd.DataFrame,
    artifact_path: str | Path,
) -> pd.DataFrame:
    return apply_signal_ml_filter(
        features_df=features_df,
        regime_df=regime_df,
        signals_df=signals_df,
        artifact_path=artifact_path,
    )
