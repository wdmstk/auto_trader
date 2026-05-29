from __future__ import annotations

from datetime import UTC, datetime

import pytest

from auto_trader.data.ohlcv import (
    build_quality_report,
    normalize_binance_klines,
    validate_ohlcv_values,
)


def test_normalize_binance_klines_uses_close_time_utc() -> None:
    klines = [
        # open_time, open, high, low, close, volume, close_time, ...
        [1000, "1.0", "2.0", "0.5", "1.5", "10.0", 61000, "0", 0, "0", "0", "0"],
    ]
    records = normalize_binance_klines(symbol="BTCUSDT", timeframe="1m", klines=klines)
    assert records[0].timestamp == datetime.fromtimestamp(61, tz=UTC)


def test_quality_report_detects_missing_and_duplicates() -> None:
    klines = [
        [0, "1", "2", "1", "2", "5", 60_000, "0", 0, "0", "0", "0"],
        [60_000, "2", "3", "2", "3", "6", 120_000, "0", 0, "0", "0", "0"],
        [180_000, "3", "4", "3", "4", "7", 240_000, "0", 0, "0", "0", "0"],
        [180_000, "3", "4", "3", "4", "7", 240_000, "0", 0, "0", "0", "0"],
    ]
    records = normalize_binance_klines(symbol="BTCUSDT", timeframe="1m", klines=klines)
    report = build_quality_report(records, "1m")
    assert report.duplicate_count == 1
    assert report.missing_count == 1
    assert report.last_synced_ts == datetime.fromtimestamp(240, tz=UTC)


def test_validate_ohlcv_rejects_invalid_values() -> None:
    invalid_klines = [
        [0, "1", "0.5", "1.0", "1.5", "1.0", 60_000, "0", 0, "0", "0", "0"],
    ]
    records = normalize_binance_klines(symbol="BTCUSDT", timeframe="1m", klines=invalid_klines)
    with pytest.raises(ValueError, match="high < low"):
        validate_ohlcv_values(records)
