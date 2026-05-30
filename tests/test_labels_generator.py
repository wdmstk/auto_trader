from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from auto_trader.labels.generator import (
    LabelConfig,
    generate_tp_sl_labels,
    validate_no_leakage,
    validate_timestamp_integrity,
)


def _ohlcv_sample() -> pd.DataFrame:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    closes = [100, 101, 102, 103, 104, 105]
    highs = [100.2, 101.1, 104.5, 103.2, 104.2, 105.2]
    lows = [99.8, 100.5, 101.5, 97.0, 103.5, 104.7]
    for i in range(len(closes)):
        rows.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": base + timedelta(minutes=i),
                "open": closes[i] - 0.1,
                "high": highs[i],
                "low": lows[i],
                "close": closes[i],
                "volume": 1000 + i,
            }
        )
    return pd.DataFrame(rows)


def test_generate_tp_sl_binary_labels() -> None:
    df = _ohlcv_sample()
    cfg = LabelConfig(tp_pct=0.02, sl_pct=0.02, max_horizon_bars=3)
    labels = generate_tp_sl_labels(df, cfg)
    assert "label" in labels.columns
    valid_values = labels["label"].dropna().isin([0, 1]).all()
    assert valid_values


def test_timestamp_integrity_rejects_duplicates() -> None:
    df = _ohlcv_sample()
    df.loc[1, "timestamp"] = df.loc[0, "timestamp"]
    with pytest.raises(ValueError, match="duplicate timestamp"):
        validate_timestamp_integrity(df)


def test_leakage_validation_checks_feature_alignment() -> None:
    labels = generate_tp_sl_labels(_ohlcv_sample(), LabelConfig(max_horizon_bars=2))
    features = labels[["symbol", "timeframe", "timestamp"]].copy()
    validate_no_leakage(features, labels)

    bad_features = features.iloc[1:].copy()
    with pytest.raises(ValueError, match="align"):
        validate_no_leakage(bad_features, labels)
