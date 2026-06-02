from __future__ import annotations

import json
from datetime import UTC, datetime
from email.message import Message
from io import BytesIO
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs
from urllib.request import Request

from pytest import MonkeyPatch

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
    seen: dict[str, object] = {}

    def sender(_: Request, __: float) -> str:
        seen["headers"] = dict(_.header_items())
        body = cast(bytes, _.data or b"").decode("utf-8")
        seen["body"] = body
        return json.dumps({"orderId": "12345", "status": "NEW"}, ensure_ascii=True)

    t = BinanceRestTransport(
        RestClientConfig(
            base_url="https://example.com",
            order_path="/api/v3/order",
            api_key="k",
            api_secret="s",
        ),
        sender=sender,
    )
    ok, order_id, reason = t.send_order(_order())
    assert ok is True
    assert order_id == "12345"
    assert reason.startswith("accepted:")
    headers = seen["headers"]
    assert isinstance(headers, dict)
    assert headers.get("X-mbx-apikey") == "k"
    params = parse_qs(str(seen["body"]))
    assert "signature" in params
    assert params["symbol"] == ["BTCUSDT"]
    assert params["newClientOrderId"] == ["cid_001"]
    assert params["type"] == ["MARKET"]


def test_rest_transport_sends_limit_ioc_fields() -> None:
    seen: dict[str, object] = {}

    def sender(req: Request, __: float) -> str:
        seen["body"] = cast(bytes, req.data or b"").decode("utf-8")
        return json.dumps({"orderId": "67890", "status": "NEW"}, ensure_ascii=True)

    t = BinanceRestTransport(
        RestClientConfig(
            base_url="https://example.com",
            order_path="/api/v3/order",
            api_key="k",
            api_secret="s",
        ),
        sender=sender,
    )
    order = OrderRequest(
        **{
            **_order().__dict__,
            "order_type": "limit",
            "limit_price": 65000.5,
        }
    )
    ok, order_id, reason = t.send_order(order)
    assert ok is True
    assert order_id == "67890"
    assert reason.startswith("accepted:")
    params = parse_qs(str(seen["body"]))
    assert params["type"] == ["LIMIT"]
    assert params["timeInForce"] == ["IOC"]
    assert params["price"] == ["65000.5"]


def test_rest_transport_uses_configured_order_path() -> None:
    seen: dict[str, object] = {}

    def sender(req: Request, __: float) -> str:
        seen["url"] = req.full_url
        return json.dumps({"orderId": "12345", "status": "NEW"}, ensure_ascii=True)

    t = BinanceRestTransport(
        RestClientConfig(
            base_url="https://example.com",
            order_path="/fapi/v1/order",
            api_key="k",
            api_secret="s",
        ),
        sender=sender,
    )
    ok, _, _ = t.send_order(_order())
    assert ok is True
    assert seen["url"] == "https://example.com/fapi/v1/order"


def test_rest_transport_handles_network_error() -> None:
    def sender(_: Request, __: float) -> str:
        raise URLError("down")

    t = BinanceRestTransport(RestClientConfig(api_key="k", api_secret="s"), sender=sender)
    ok, order_id, reason = t.send_order(_order())
    assert ok is False
    assert order_id == ""
    assert reason == "network_error"


def test_rest_transport_handles_missing_credentials() -> None:
    t = BinanceRestTransport(RestClientConfig(api_key="", api_secret=""))
    ok, order_id, reason = t.send_order(_order())
    assert ok is False
    assert order_id == ""
    assert reason == "credentials_missing"


def test_rest_transport_rejects_limit_without_price() -> None:
    t = BinanceRestTransport(RestClientConfig(api_key="k", api_secret="s"))
    order = OrderRequest(
        **{
            **_order().__dict__,
            "order_type": "limit",
            "limit_price": None,
        }
    )
    ok, order_id, reason = t.send_order(order)
    assert ok is False
    assert order_id == ""
    assert reason == "invalid_order_request:limit_price_required"


def test_rest_transport_applies_timestamp_offset(monkeypatch: MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr("auto_trader.exchange.rest_client.time.time", lambda: 100.0)

    def sender(req: Request, __: float) -> str:
        body = cast(bytes, req.data or b"").decode("utf-8")
        seen["body"] = body
        return json.dumps({"orderId": "12345", "status": "NEW"}, ensure_ascii=True)

    t = BinanceRestTransport(
        RestClientConfig(
            base_url="https://example.com",
            order_path="/api/v3/order",
            api_key="k",
            api_secret="s",
            timestamp_offset_ms=1234,
        ),
        sender=sender,
    )
    ok, _, _ = t.send_order(_order())
    assert ok is True
    params = parse_qs(str(seen["body"]))
    assert params["timestamp"] == ["101234"]


def test_rest_transport_surfaces_http_error_detail() -> None:
    def sender(req: Request, _: float) -> str:
        raise HTTPError(
            url=req.full_url,
            code=400,
            msg="Bad Request",
            hdrs=Message(),
            fp=BytesIO(b'{"code":-2015,"msg":"Invalid API-key, IP, or permissions for action."}'),
        )

    t = BinanceRestTransport(RestClientConfig(api_key="k", api_secret="s"), sender=sender)
    ok, order_id, reason = t.send_order(_order())
    assert ok is False
    assert order_id == ""
    assert reason.startswith("http_error:400")
    assert "code=-2015" in reason
