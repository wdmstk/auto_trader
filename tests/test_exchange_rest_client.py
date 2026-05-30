from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.error import URLError
from urllib.request import Request

from auto_trader.exchange.models import OrderRequest
from auto_trader.exchange.rest_client import BinanceRestTransport, RestClientConfig


def _order() -> OrderRequest:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    return OrderRequest(
        symbol="BTCUSDT",
        side="buy",
        qty=0.1,
        signal_ts=ts,
        regime="RANGE",
        pass_filter=True,
        client_order_id="cid_001",
    )


def test_rest_transport_accepts_valid_response() -> None:
    def sender(_: Request, __: float) -> str:
        return json.dumps({"orderId": "12345", "status": "NEW"}, ensure_ascii=True)

    t = BinanceRestTransport(RestClientConfig(base_url="https://example.com"), sender=sender)
    ok, order_id, reason = t.send_order(_order())
    assert ok is True
    assert order_id == "12345"
    assert reason.startswith("accepted:")


def test_rest_transport_handles_network_error() -> None:
    def sender(_: Request, __: float) -> str:
        raise URLError("down")

    t = BinanceRestTransport(sender=sender)
    ok, order_id, reason = t.send_order(_order())
    assert ok is False
    assert order_id == ""
    assert reason == "network_error"
