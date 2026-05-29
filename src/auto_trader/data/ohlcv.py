from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

TIMEFRAME_TO_DELTA: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "3m": timedelta(minutes=3),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "4h": timedelta(hours=4),
    "6h": timedelta(hours=6),
    "8h": timedelta(hours=8),
    "12h": timedelta(hours=12),
    "1d": timedelta(days=1),
}


@dataclass(frozen=True)
class OhlcvRecord:
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str
    ingested_at: datetime


@dataclass(frozen=True)
class DataQualityReport:
    missing_count: int
    duplicate_count: int
    gap_ranges: list[tuple[datetime, datetime]]
    last_synced_ts: datetime | None


def timeframe_to_delta(timeframe: str) -> timedelta:
    if timeframe not in TIMEFRAME_TO_DELTA:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    return TIMEFRAME_TO_DELTA[timeframe]


def ms_to_utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def utc_to_ms(ts: datetime) -> int:
    if ts.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return int(ts.timestamp() * 1000)


def normalize_binance_klines(
    *,
    symbol: str,
    timeframe: str,
    klines: list[list[Any]],
    source: str = "binance_rest",
    ingested_at: datetime | None = None,
) -> list[OhlcvRecord]:
    now = ingested_at or datetime.now(UTC)
    records: list[OhlcvRecord] = []
    for row in klines:
        if len(row) < 7:
            raise ValueError("kline row must have at least 7 columns")
        close_time_ms = int(row[6])
        record = OhlcvRecord(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=ms_to_utc(close_time_ms),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            source=source,
            ingested_at=now,
        )
        records.append(record)
    return sorted(records, key=lambda x: x.timestamp)


def validate_ohlcv_values(records: list[OhlcvRecord]) -> None:
    for record in records:
        if record.high < record.low:
            raise ValueError("invalid ohlcv row: high < low")
        if record.volume < 0:
            raise ValueError("invalid ohlcv row: volume < 0")


def count_duplicates(records: list[OhlcvRecord]) -> int:
    seen: set[tuple[str, str, datetime]] = set()
    duplicates = 0
    for record in records:
        key = (record.symbol, record.timeframe, record.timestamp)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates


def deduplicate_records(records: list[OhlcvRecord]) -> list[OhlcvRecord]:
    unique: dict[tuple[str, str, datetime], OhlcvRecord] = {}
    for record in records:
        unique[(record.symbol, record.timeframe, record.timestamp)] = record
    return sorted(unique.values(), key=lambda x: x.timestamp)


def detect_missing_ranges(
    records: list[OhlcvRecord],
    timeframe: str,
) -> list[tuple[datetime, datetime]]:
    if len(records) < 2:
        return []
    step = timeframe_to_delta(timeframe)
    gaps: list[tuple[datetime, datetime]] = []
    sorted_records = sorted(records, key=lambda x: x.timestamp)
    for prev, curr in zip(sorted_records, sorted_records[1:], strict=False):
        delta = curr.timestamp - prev.timestamp
        if delta > step:
            gap_start = prev.timestamp + step
            gap_end = curr.timestamp - step
            gaps.append((gap_start, gap_end))
    return gaps


def build_quality_report(records: list[OhlcvRecord], timeframe: str) -> DataQualityReport:
    duplicates = count_duplicates(records)
    deduped = deduplicate_records(records)
    gaps = detect_missing_ranges(deduped, timeframe)
    return DataQualityReport(
        missing_count=sum(_count_missing_in_gap(start, end, timeframe) for start, end in gaps),
        duplicate_count=duplicates,
        gap_ranges=gaps,
        last_synced_ts=deduped[-1].timestamp if deduped else None,
    )


def _count_missing_in_gap(start: datetime, end: datetime, timeframe: str) -> int:
    step = timeframe_to_delta(timeframe)
    if end < start:
        return 0
    return int((end - start) / step) + 1
