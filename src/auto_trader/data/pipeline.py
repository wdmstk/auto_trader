from __future__ import annotations

from auto_trader.data.ohlcv import (
    DataQualityReport,
    OhlcvRecord,
    build_quality_report,
    deduplicate_records,
    validate_ohlcv_values,
)
from auto_trader.data.parquet_store import OhlcvParquetStore


def validate_and_report(records: list[OhlcvRecord], timeframe: str) -> DataQualityReport:
    validate_ohlcv_values(records)
    return build_quality_report(records, timeframe)


def save_normalized_ohlcv(
    *,
    store: OhlcvParquetStore,
    symbol: str,
    timeframe: str,
    records: list[OhlcvRecord],
) -> tuple[DataQualityReport, str]:
    report = validate_and_report(records, timeframe)
    deduped = deduplicate_records(records)
    path = store.upsert(symbol=symbol, timeframe=timeframe, records=deduped)
    return report, str(path)
