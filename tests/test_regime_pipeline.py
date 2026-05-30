from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.regime.pipeline import classify_and_save_regime


def test_classify_and_save_regime(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for i in range(70):
        rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": base + timedelta(minutes=i),
                "atr": 1.0 + (0.01 * i),
                "bb_width": 0.05,
                "mean_reversion_distance": 0.3,
                "momentum_persistence": 0.4,
                "breakout_persistence": 0.4,
                "trend_efficiency": 0.2,
                "is_warmup": i < 10,
            }
        )
    feature_df = pd.DataFrame(rows)
    feature_path = tmp_path / "ETHUSDT_1m_features.parquet"
    feature_df.to_parquet(feature_path, index=False)

    regime_df, saved_path = classify_and_save_regime(
        feature_path=feature_path,
        symbol="ETHUSDT",
        timeframe="1m",
        output_dir=tmp_path / "regime",
    )

    assert len(regime_df) == len(feature_df)
    assert Path(saved_path).exists()
    assert regime_df["is_trade_allowed"].isin([True, False]).all()
