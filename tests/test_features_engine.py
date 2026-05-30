from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from auto_trader.features.engine import FeatureConfig, compute_features


def _sample_ohlcv(rows: int = 80) -> pd.DataFrame:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    items: list[dict[str, object]] = []
    price = 100.0
    for i in range(rows):
        ts = base + timedelta(minutes=i)
        price = price + 0.2
        items.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "open": price - 0.1,
                "high": price + 0.3,
                "low": price - 0.4,
                "close": price,
                "volume": 1000 + i,
                "source": "test",
                "ingested_at": base,
            }
        )
    return pd.DataFrame(items)


def test_compute_features_has_required_columns() -> None:
    df = _sample_ohlcv(90)
    out = compute_features(df, FeatureConfig(min_history_bars=30))
    required = {
        "symbol",
        "timeframe",
        "timestamp",
        "rsi",
        "atr",
        "bb_width",
        "volume_ratio",
        "ma_distance",
        "trend_efficiency",
        "wick_ratio",
        "mean_reversion_distance",
        "reversal_candle_flag",
        "momentum_persistence",
        "breakout_persistence",
        "pullback_shallowness",
        "higher_high_persistence",
        "feature_version",
        "generated_at",
        "is_warmup",
    }
    assert required.issubset(set(out.columns))
    assert len(out) == len(df)


def test_warmup_flag_applied() -> None:
    df = _sample_ohlcv(60)
    out = compute_features(df, FeatureConfig(min_history_bars=50))
    assert int(out["is_warmup"].sum()) == 50


def test_no_future_leakage_order_preserved() -> None:
    df = _sample_ohlcv(70).sample(frac=1.0, random_state=7)
    out = compute_features(df)
    ts = pd.to_datetime(out["timestamp"], utc=True)
    assert ts.is_monotonic_increasing
