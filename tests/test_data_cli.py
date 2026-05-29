from __future__ import annotations

from datetime import UTC, datetime

from auto_trader.data.cli import _parse_utc, build_parser


def test_parse_utc_from_naive_iso() -> None:
    dt = _parse_utc("2026-01-01T00:00:00")
    assert dt == datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


def test_parse_utc_from_offset_iso() -> None:
    dt = _parse_utc("2026-01-01T09:00:00+09:00")
    assert dt == datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


def test_build_parser_required_args() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--symbol",
            "BTCUSDT",
            "--timeframe",
            "1m",
            "--from-ts",
            "2026-01-01T00:00:00+00:00",
            "--to-ts",
            "2026-01-01T01:00:00+00:00",
        ]
    )
    assert args.symbol == "BTCUSDT"
    assert args.timeframe == "1m"
