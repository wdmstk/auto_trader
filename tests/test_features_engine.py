from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from auto_trader.features.engine import (
    FeatureConfig,
    compute_features,
    compute_htf_sr_features,
    overlay_htf_sr,
)


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


def _make_htf_ltf_data() -> (
    tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]
):
    """Create synthetic 4h (HTF) and 15m (LTF) data with a clear support level."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    n_htf = 60  # 60 x 4h bars = 10 days

    # HTF: zigzag with support at 100, resistance at 110
    htf_close = np.empty(n_htf)
    htf_high = np.empty(n_htf)
    htf_low = np.empty(n_htf)
    htf_timestamps = np.array(
        [np.datetime64(base + timedelta(hours=4 * i), "ns") for i in range(n_htf)]
    )
    for i in range(n_htf):
        cycle = i % 20
        if cycle < 10:
            price = 100.0 + cycle * 1.0  # 100 -> 110
        else:
            price = 110.0 - (cycle - 10) * 1.0  # 110 -> 100
        htf_close[i] = price
        htf_high[i] = price + 0.5
        htf_low[i] = price - 0.5

    # LTF: 16 x 15m bars per 4h, total n_htf * 16
    n_ltf = n_htf * 16
    ltf_timestamps = np.array(
        [np.datetime64(base + timedelta(minutes=15 * i), "ns") for i in range(n_ltf)]
    )
    # LTF close hovers around 101 (near support)
    ltf_close = np.full(n_ltf, 101.0)
    ltf_atr = np.full(n_ltf, 1.0)  # constant ATR for easy distance checks

    return htf_high, htf_low, htf_close, htf_timestamps, ltf_close, ltf_atr, ltf_timestamps


def test_compute_htf_sr_features_basic() -> None:
    """HTF S/R detection should find levels and compute distances at LTF."""
    htf_high, htf_low, htf_close, htf_ts, ltf_close, ltf_atr, ltf_ts = _make_htf_ltf_data()

    result = compute_htf_sr_features(
        htf_high=htf_high,
        htf_low=htf_low,
        htf_close=htf_close,
        htf_timestamps=htf_ts,
        ltf_close=ltf_close,
        ltf_atr=ltf_atr,
        ltf_timestamps=ltf_ts,
        pivot_left=3,
        pivot_right=3,
        cluster_atr_mult=0.5,
        max_levels=10,
        max_age=500,
    )

    assert "sr_support_distance" in result
    assert "sr_resistance_distance" in result
    assert "sr_level_strength" in result
    assert len(result["sr_support_distance"]) == len(ltf_close)

    # After enough bars for pivot detection, should have some non-NaN distances
    sup = result["sr_support_distance"]
    res = result["sr_resistance_distance"]
    assert np.any(~np.isnan(sup)), "Expected some support distances computed"
    assert np.any(~np.isnan(res)), "Expected some resistance distances computed"

    # Distances should be non-negative
    assert np.all(sup[~np.isnan(sup)] >= 0)
    assert np.all(res[~np.isnan(res)] >= 0)


def test_htf_sr_no_future_leakage() -> None:
    """Levels detected at HTF bar N should not appear before that bar closes."""
    htf_high, htf_low, htf_close, htf_ts, ltf_close, ltf_atr, ltf_ts = _make_htf_ltf_data()

    result = compute_htf_sr_features(
        htf_high=htf_high,
        htf_low=htf_low,
        htf_close=htf_close,
        htf_timestamps=htf_ts,
        ltf_close=ltf_close,
        ltf_atr=ltf_atr,
        ltf_timestamps=ltf_ts,
        pivot_left=3,
        pivot_right=3,
        cluster_atr_mult=0.5,
        max_levels=10,
        max_age=500,
    )

    # First few LTF bars (before any HTF bar completes) should have NaN/0
    # Pivot needs at least pivot_left + pivot_right + 1 = 7 HTF bars
    # 7 HTF bars = 7 * 16 = 112 LTF bars before any pivot is possible
    early_sup = result["sr_support_distance"][:50]
    assert np.all(np.isnan(early_sup)), "No levels should exist before HTF has enough bars"


def test_overlay_htf_sr() -> None:
    """overlay_htf_sr should replace S/R columns with HTF-derived values."""
    base = datetime(2026, 1, 1, tzinfo=UTC)

    # Create LTF OHLCV (15m, 200 bars)
    n_ltf = 200
    ltf_items = []
    for i in range(n_ltf):
        ts = base + timedelta(minutes=15 * i)
        price = 101.0 + 0.1 * (i % 10)
        ltf_items.append({
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "timestamp": ts,
            "open": price - 0.05,
            "high": price + 0.2,
            "low": price - 0.2,
            "close": price,
            "volume": 1000.0,
            "source": "test",
            "ingested_at": base,
        })
    ltf_ohlcv = pd.DataFrame(ltf_items)

    # Create HTF OHLCV (4h, covers same period)
    n_htf = 60
    htf_items = []
    for i in range(n_htf):
        ts = base + timedelta(hours=4 * i)
        cycle = i % 20
        if cycle < 10:
            price = 100.0 + cycle * 1.0
        else:
            price = 110.0 - (cycle - 10) * 1.0
        htf_items.append({
            "symbol": "BTCUSDT",
            "timeframe": "4h",
            "timestamp": ts,
            "open": price - 0.1,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": 5000.0,
        })
    htf_ohlcv = pd.DataFrame(htf_items)

    # Compute features on LTF
    features = compute_features(ltf_ohlcv, FeatureConfig(min_history_bars=20, sr_pivot_left_bars=3, sr_pivot_right_bars=3))

    # Apply HTF overlay
    result = overlay_htf_sr(features, htf_ohlcv, ltf_ohlcv, FeatureConfig(sr_pivot_left_bars=3, sr_pivot_right_bars=3))

    # Result should have same shape
    assert len(result) == len(features)
    assert "sr_support_distance" in result.columns
    assert "sr_resistance_distance" in result.columns

    # HTF overlay might produce different values from same-TF
    # (can't guarantee they differ with synthetic data, but should not crash)
