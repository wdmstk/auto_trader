from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_trader.data.binance_client import (
    BinanceKlineClient,
    download_historical_ohlcv,
    download_incremental_ohlcv,
)
from auto_trader.data.ohlcv import timeframe_to_delta, utc_to_ms
from auto_trader.data.parquet_store import OhlcvParquetStore
from auto_trader.data.pipeline import save_normalized_ohlcv


class FakeBinanceClient(BinanceKlineClient):
    def __init__(self) -> None:
        super().__init__(base_url="https://example.com")
        self.calls: list[tuple[int, int]] = []

    def fetch_with_retry(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 1000,
        max_retries: int = 4,
        base_backoff_sec: float = 0.5,
    ) -> list[list[object]]:
        self.calls.append((start_time_ms, end_time_ms))
        del symbol, interval, limit, max_retries, base_backoff_sec
        return [
            [
                0,
                "1.0",
                "2.0",
                "0.5",
                "1.5",
                "10.0",
                end_time_ms,
                "0",
                0,
                "0",
                "0",
                "0",
            ]
        ]


class PagingFakeBinanceClient(BinanceKlineClient):
    def __init__(self, *, timeframe: str, from_ts: datetime, bars: int) -> None:
        super().__init__(base_url="https://example.com")
        self.calls: list[tuple[int, int, int]] = []
        step = timeframe_to_delta(timeframe)
        self.klines: list[list[object]] = []
        for index in range(bars):
            open_ts = from_ts + (step * index)
            close_ts = open_ts + step - timedelta(milliseconds=1)
            self.klines.append(
                [
                    utc_to_ms(open_ts),
                    "1.0",
                    "2.0",
                    "0.5",
                    "1.5",
                    "10.0",
                    utc_to_ms(close_ts),
                    "0",
                    0,
                    "0",
                    "0",
                    "0",
                ]
            )

    def fetch_with_retry(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 1000,
        max_retries: int = 4,
        base_backoff_sec: float = 0.5,
    ) -> list[list[object]]:
        del symbol, interval, max_retries, base_backoff_sec
        self.calls.append((start_time_ms, end_time_ms, limit))
        rows = [row for row in self.klines if start_time_ms <= int(str(row[6])) <= end_time_ms]
        return rows[:limit]


def test_historical_and_incremental_download_flow() -> None:
    client = FakeBinanceClient()
    from_ts = datetime(2026, 1, 1, tzinfo=UTC)
    to_ts = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)

    historical = download_historical_ohlcv(
        client=client,
        symbol="BTCUSDT",
        timeframe="1m",
        from_ts=from_ts,
        to_ts=to_ts,
    )
    assert historical

    incremental = download_incremental_ohlcv(
        client=client,
        symbol="BTCUSDT",
        timeframe="1m",
        last_synced_ts=historical[-1].timestamp,
        to_ts=datetime(2026, 1, 1, 0, 10, tzinfo=UTC),
    )
    assert incremental
    assert len(client.calls) >= 2


def test_parquet_upsert_and_quality_report(tmp_path: Path) -> None:
    client = FakeBinanceClient()
    records = download_historical_ohlcv(
        client=client,
        symbol="ETHUSDT",
        timeframe="1m",
        from_ts=datetime(2026, 1, 1, tzinfo=UTC),
        to_ts=datetime(2026, 1, 1, 0, 2, tzinfo=UTC),
    )
    store = OhlcvParquetStore(tmp_path)
    report, saved_path = save_normalized_ohlcv(
        store=store,
        symbol="ETHUSDT",
        timeframe="1m",
        records=records,
    )

    assert report.duplicate_count == 0
    assert report.last_synced_ts is not None
    assert Path(saved_path).exists()

    loaded = store.read("ETHUSDT", "1m")
    assert len(loaded) == len(records)


def test_historical_download_paginates_beyond_exchange_limit() -> None:
    from_ts = datetime(2026, 1, 1, tzinfo=UTC)
    bars = 3 * 24 * 60
    client = PagingFakeBinanceClient(timeframe="1m", from_ts=from_ts, bars=bars)

    records = download_historical_ohlcv(
        client=client,
        symbol="BTCUSDT",
        timeframe="1m",
        from_ts=from_ts,
        to_ts=from_ts + timedelta(days=3),
        chunk_span=timedelta(days=3),
    )

    assert len(records) == bars
    assert len(client.calls) >= 3
    assert records[0].timestamp == from_ts + timedelta(minutes=1) - timedelta(milliseconds=1)
    assert records[-1].timestamp == from_ts + timedelta(days=3) - timedelta(milliseconds=1)
