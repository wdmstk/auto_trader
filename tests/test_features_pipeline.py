from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.features.engine import FeatureConfig
from auto_trader.features.pipeline import generate_and_save_features


def test_generate_and_save_features_from_parquet(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for i in range(80):
        p = 100 + i * 0.1
        rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": base + timedelta(minutes=i),
                "open": p - 0.2,
                "high": p + 0.3,
                "low": p - 0.5,
                "close": p,
                "volume": 500 + i,
                "source": "test",
                "ingested_at": base,
            }
        )

    ohlcv_df = pd.DataFrame(rows)
    ohlcv_path = tmp_path / "ETHUSDT_1m.parquet"
    ohlcv_df.to_parquet(ohlcv_path, index=False)

    features, saved_path = generate_and_save_features(
        ohlcv_path=ohlcv_path,
        symbol="ETHUSDT",
        timeframe="1m",
        output_dir=tmp_path / "features",
        config=FeatureConfig(feature_version="v1-test", min_history_bars=10),
    )

    assert len(features) == len(ohlcv_df)
    assert (features["feature_version"] == "v1-test").all()
    assert Path(saved_path).exists()
