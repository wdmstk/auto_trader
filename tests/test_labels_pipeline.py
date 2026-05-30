from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.labels.generator import LabelConfig
from auto_trader.labels.pipeline import generate_and_save_labels


def test_generate_and_save_labels(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for i in range(40):
        price = 100 + i * 0.2
        rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": base + timedelta(minutes=i),
                "open": price - 0.1,
                "high": price + 0.4,
                "low": price - 0.4,
                "close": price,
                "volume": 500 + i,
            }
        )
    ohlcv = pd.DataFrame(rows)
    ohlcv_path = tmp_path / "ETHUSDT_1m.parquet"
    ohlcv.to_parquet(ohlcv_path, index=False)

    features = ohlcv[["symbol", "timeframe", "timestamp"]].copy()
    features_path = tmp_path / "ETHUSDT_1m_features.parquet"
    features.to_parquet(features_path, index=False)

    labels, saved_path = generate_and_save_labels(
        ohlcv_path=ohlcv_path,
        symbol="ETHUSDT",
        timeframe="1m",
        output_dir=tmp_path / "labels",
        config=LabelConfig(tp_pct=0.01, sl_pct=0.01, max_horizon_bars=10),
        features_path=features_path,
    )
    assert len(labels) == len(ohlcv)
    assert Path(saved_path).exists()
    assert "label_reason" in labels.columns
