from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from auto_trader.data.ohlcv import (
    OhlcvRecord,
    normalize_binance_klines,
    timeframe_to_delta,
    utc_to_ms,
)


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

    def fetch_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.base_url}{path}{query}"
        request = Request(url, headers={"User-Agent": "auto-trader/0.1"})
        with urlopen(request, timeout=self.timeout_sec) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload)

    def fetch_exchange_info(self) -> dict[str, Any]:
        result = self.fetch_json("/api/v3/exchangeInfo")
        if not isinstance(result, dict):
            raise ValueError("unexpected exchangeInfo response from Binance")
        return result

    def fetch_24h_tickers(self) -> list[dict[str, Any]]:
        result = self.fetch_json("/api/v3/ticker/24hr")
        if not isinstance(result, list):
            raise ValueError("unexpected 24hr ticker response from Binance")
        return [row for row in result if isinstance(row, dict)]

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
    step_ms = int(timeframe_to_delta(timeframe).total_seconds() * 1000)
    while cursor < end:
        chunk_end = min(cursor + chunk_span, end)
        page_start_ms = utc_to_ms(cursor)
        chunk_end_ms = utc_to_ms(chunk_end)
        while page_start_ms < chunk_end_ms:
            rows = client.fetch_with_retry(
                symbol=symbol,
                interval=timeframe,
                start_time_ms=page_start_ms,
                end_time_ms=chunk_end_ms,
            )
            if not rows:
                break
            all_rows.extend(rows)
            last_close_time_ms = int(rows[-1][6])
            next_page_start_ms = last_close_time_ms + 1
            if next_page_start_ms <= page_start_ms:
                next_page_start_ms = page_start_ms + step_ms
            if len(rows) < 1000:
                break
            page_start_ms = next_page_start_ms
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
