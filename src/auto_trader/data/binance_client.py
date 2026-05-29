from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from auto_trader.data.ohlcv import OhlcvRecord, normalize_binance_klines, utc_to_ms


class BinanceKlineClient:
    def __init__(
        self,
        base_url: str = "https://api.binance.com",
        timeout_sec: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    def fetch_klines(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 1000,
    ) -> list[list[Any]]:
        params = urlencode(
            {
                "symbol": symbol,
                "interval": interval,
                "startTime": start_time_ms,
                "endTime": end_time_ms,
                "limit": limit,
            }
        )
        url = f"{self.base_url}/api/v3/klines?{params}"
        request = Request(url, headers={"User-Agent": "auto-trader/0.1"})
        with urlopen(request, timeout=self.timeout_sec) as response:
            payload = response.read().decode("utf-8")
            result = json.loads(payload)
            if not isinstance(result, list):
                raise ValueError("unexpected response from Binance")
            return result

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
    ) -> list[list[Any]]:
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return self.fetch_klines(
                    symbol=symbol,
                    interval=interval,
                    start_time_ms=start_time_ms,
                    end_time_ms=end_time_ms,
                    limit=limit,
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt == max_retries:
                    break
                time.sleep(base_backoff_sec * (2**attempt))
        assert last_exc is not None
        raise last_exc


def download_historical_ohlcv(
    *,
    client: BinanceKlineClient,
    symbol: str,
    timeframe: str,
    from_ts: datetime,
    to_ts: datetime,
    chunk_span: timedelta = timedelta(days=3),
) -> list[OhlcvRecord]:
    if from_ts.tzinfo is None or to_ts.tzinfo is None:
        raise ValueError("from_ts and to_ts must be timezone-aware")
    if from_ts >= to_ts:
        raise ValueError("from_ts must be before to_ts")

    all_rows: list[list[Any]] = []
    cursor = from_ts.astimezone(UTC)
    end = to_ts.astimezone(UTC)
    while cursor < end:
        chunk_end = min(cursor + chunk_span, end)
        rows = client.fetch_with_retry(
            symbol=symbol,
            interval=timeframe,
            start_time_ms=utc_to_ms(cursor),
            end_time_ms=utc_to_ms(chunk_end),
        )
        all_rows.extend(rows)
        cursor = chunk_end
    return normalize_binance_klines(symbol=symbol, timeframe=timeframe, klines=all_rows)


def download_incremental_ohlcv(
    *,
    client: BinanceKlineClient,
    symbol: str,
    timeframe: str,
    last_synced_ts: datetime,
    to_ts: datetime,
) -> list[OhlcvRecord]:
    start = last_synced_ts + timedelta(milliseconds=1)
    return download_historical_ohlcv(
        client=client,
        symbol=symbol,
        timeframe=timeframe,
        from_ts=start,
        to_ts=to_ts,
    )
