from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.strategy.pipeline import build_and_save_range_signals


def test_build_and_save_range_signals(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    feats: list[dict[str, object]] = []
    regimes: list[dict[str, object]] = []
    for i in range(20):
        ts = base + timedelta(minutes=i)
        feats.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "rsi": 45.0,
                "wick_ratio": 0.7,
                "mean_reversion_distance": -0.2,
                "reversal_candle_flag": 1,
            }
        )
        regimes.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "regime": "RANGE",
                "is_trade_allowed": True,
                "confidence": 0.8,
            }
        )
    fpath = tmp_path / "features.parquet"
    rpath = tmp_path / "regime.parquet"
    pd.DataFrame(feats).to_parquet(fpath, index=False)
    pd.DataFrame(regimes).to_parquet(rpath, index=False)

    out, saved = build_and_save_range_signals(
        features_path=fpath,
        regime_path=rpath,
        symbol="ETHUSDT",
        timeframe="1m",
        output_dir=tmp_path / "signals",
    )
    assert len(out) == 20
    assert Path(saved).exists()
    assert "entry_signal" in out.columns
