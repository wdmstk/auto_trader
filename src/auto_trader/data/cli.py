from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from auto_trader.data.binance_client import BinanceKlineClient, download_historical_ohlcv
from auto_trader.data.parquet_store import OhlcvParquetStore
from auto_trader.data.pipeline import save_normalized_ohlcv


def _parse_utc(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download Binance OHLCV and save to parquet.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--from-ts", required=True, help="ISO8601 UTC timestamp")
    parser.add_argument("--to-ts", required=True, help="ISO8601 UTC timestamp")
    parser.add_argument("--output-dir", default="data/parquet")
    parser.add_argument("--base-url", default="https://api.binance.com")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    from_ts = _parse_utc(args.from_ts)
    to_ts = _parse_utc(args.to_ts)

    client = BinanceKlineClient(base_url=args.base_url)
    records = download_historical_ohlcv(
        client=client,
        symbol=args.symbol,
        timeframe=args.timeframe,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    store = OhlcvParquetStore(Path(args.output_dir))
    report, saved_path = save_normalized_ohlcv(
        store=store,
        symbol=args.symbol,
        timeframe=args.timeframe,
        records=records,
    )

    print(
        f"saved={saved_path} rows={len(records)} missing={report.missing_count} "
        f"duplicates={report.duplicate_count} last_synced_ts={report.last_synced_ts}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
