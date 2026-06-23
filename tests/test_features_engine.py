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
        "sr_support_distance",
        "sr_resistance_distance",
        "sr_level_strength",
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


def _sample_ohlcv_with_swing(rows: int = 120) -> pd.DataFrame:
    """Generate data with clear swing highs and lows for S/R detection."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    items: list[dict[str, object]] = []
    price = 100.0
    for i in range(rows):
        ts = base + timedelta(minutes=i)
        # Zigzag: create swing lows near i=20,60 and swing highs near i=40,80
        cycle = i % 40
        if cycle < 20:
            price = 100.0 + cycle * 0.5
        else:
            price = 110.0 - (cycle - 20) * 0.5
        items.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "open": price - 0.1,
                "high": price + 0.3,
                "low": price - 0.3,
                "close": price,
                "volume": 1000.0,
                "source": "test",
                "ingested_at": base,
            }
        )
    return pd.DataFrame(items)


def test_sr_features_detect_levels() -> None:
    """S/R features should detect levels at swing points in zigzag data."""
    df = _sample_ohlcv_with_swing(120)
    out = compute_features(
        df,
        FeatureConfig(
            min_history_bars=20,
            sr_pivot_left_bars=3,
            sr_pivot_right_bars=3,
        ),
    )
    # After enough bars, some S/R levels should be detected
    sup_dist = out["sr_support_distance"].dropna()
    res_dist = out["sr_resistance_distance"].dropna()
    assert len(sup_dist) > 0, "Expected some support levels detected"
    assert len(res_dist) > 0, "Expected some resistance levels detected"

    # Level strength should be > 0 where levels exist
    strength_nonzero = out["sr_level_strength"][out["sr_level_strength"] > 0]
    assert len(strength_nonzero) > 0, "Expected nonzero strength at detected levels"

    # Distances should be non-negative
    assert (sup_dist >= 0).all()
    assert (res_dist >= 0).all()


def test_no_future_leakage_order_preserved() -> None:
    df = _sample_ohlcv(70).sample(frac=1.0, random_state=7)
    out = compute_features(df)
    ts = pd.to_datetime(out["timestamp"], utc=True)
    assert ts.is_monotonic_increasing
