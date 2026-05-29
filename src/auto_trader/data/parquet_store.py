from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq

from auto_trader.data.ohlcv import OhlcvRecord


def _to_row(record: OhlcvRecord) -> dict[str, object]:
    row = asdict(record)
    return row


def _record_key(row: dict[str, object]) -> tuple[str, str, datetime]:
    symbol = str(row["symbol"])
    timeframe = str(row["timeframe"])
    timestamp = row["timestamp"]
    if not isinstance(timestamp, datetime):
        raise TypeError("timestamp must be datetime")
    return (symbol, timeframe, timestamp)


class OhlcvParquetStore:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, symbol: str, timeframe: str) -> Path:
        return self.root_dir / f"{symbol}_{timeframe}.parquet"

    def read(self, symbol: str, timeframe: str) -> list[dict[str, object]]:
        path = self.path_for(symbol, timeframe)
        if not path.exists():
            return []
        table = pq.read_table(path)
        return cast(list[dict[str, object]], table.to_pylist())

    def upsert(self, symbol: str, timeframe: str, records: list[OhlcvRecord]) -> Path:
        path = self.path_for(symbol, timeframe)
        existing_rows = self.read(symbol, timeframe)
        merged: dict[tuple[str, str, datetime], dict[str, object]] = {
            _record_key(row): row for row in existing_rows
        }
        for record in records:
            row = _to_row(record)
            merged[_record_key(row)] = row

        merged_rows = [merged[key] for key in sorted(merged.keys(), key=lambda x: x[2])]
        table = pa.Table.from_pylist(merged_rows)
        pq.write_table(table, path)
        return path
