from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.drift.gate import is_drift_trade_blocked
from auto_trader.strategy.ml_filter import apply_signal_ml_filter, resolve_ml_artifact_path
from auto_trader.strategy.session_gate import apply_session_gate
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
    drift_report_path: str | Path | None = None,
    ml_artifact_path: str | Path | None = None,
    allowed_hours: str | None = None,
    config: TrendStrategyConfig | None = None,
) -> tuple[pd.DataFrame, str]:
    features = pd.read_parquet(features_path)
    regime = pd.read_parquet(regime_path)
    if is_drift_trade_blocked(drift_report_path):
        regime = regime.copy()
        regime["is_trade_allowed"] = False
    risk = pd.read_parquet(risk_path) if risk_path else None
    pnl = pd.read_parquet(pnl_path) if pnl_path else None
    signals = generate_trend_signals(
        features_df=features,
        regime_df=regime,
        risk_df=risk,
        pnl_df=pnl,
        config=config,
    )
    resolved_ml_artifact_path = resolve_ml_artifact_path(ml_artifact_path)
    if resolved_ml_artifact_path is not None:
        signals = apply_signal_ml_filter(
            features_df=features,
            regime_df=regime,
            signals_df=signals,
            artifact_path=resolved_ml_artifact_path,
        )
    if allowed_hours:
        signals = apply_session_gate(signals, allowed_hours=allowed_hours)
    store = SignalParquetStore(output_dir, strategy="trend")
    saved = store.save(symbol, timeframe, signals)
    return signals, str(saved)
