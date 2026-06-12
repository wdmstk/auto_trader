from __future__ import annotations

from pytest import MonkeyPatch

from auto_trader.worker.cli import _build_parser


def test_build_parser_defaults_worker_order_modes_to_market(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("TREND_ORDER_MODE", raising=False)
    monkeypatch.delenv("RANGE_ORDER_MODE", raising=False)

    parser = _build_parser()
    args = parser.parse_args([])

    assert args.trend_order_mode == "market"
    assert args.range_order_mode == "market"
