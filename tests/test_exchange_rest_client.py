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
        if req.full_url.endswith("/api/v3/exchangeInfo?symbol=BTCUSDT"):
            return json.dumps(
                {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                                {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                            ],
                        }
                    ]
                },
                ensure_ascii=True,
            )
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


def test_rest_transport_normalizes_qty_and_price_by_symbol_filters() -> None:
    seen: dict[str, object] = {}

    def sender(req: Request, __: float) -> str:
        if req.full_url.endswith("/api/v3/exchangeInfo?symbol=BTCUSDT"):
            return json.dumps(
                {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.5"},
                                {"filterType": "LOT_SIZE", "stepSize": "0.01", "minQty": "0.01"},
                            ],
                        }
                    ]
                },
                ensure_ascii=True,
            )
        seen["body"] = cast(bytes, req.data or b"").decode("utf-8")
        return json.dumps({"orderId": "99999", "status": "NEW"}, ensure_ascii=True)

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
            "qty": 0.123456,
            "order_type": "limit",
            "limit_price": 65000.57,
        }
    )
    ok, order_id, reason = t.send_order(order)
    assert ok is True
    assert order_id == "99999"
    assert reason.startswith("accepted:")
    params = parse_qs(str(seen["body"]))
    assert params["quantity"] == ["0.12"]
    assert params["price"] == ["65000.5"]


def test_rest_transport_rejects_qty_below_min_without_upsizing() -> None:
    order_requests = 0

    def sender(req: Request, __: float) -> str:
        nonlocal order_requests
        if req.full_url.endswith("/api/v3/exchangeInfo?symbol=BTCUSDT"):
            return json.dumps(
                {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "filters": [
                                {"filterType": "LOT_SIZE", "stepSize": "0.01", "minQty": "0.10"},
                            ],
                        }
                    ]
                },
                ensure_ascii=True,
            )
        order_requests += 1
        return json.dumps({"orderId": "unexpected", "status": "NEW"}, ensure_ascii=True)

    transport = BinanceRestTransport(
        RestClientConfig(
            base_url="https://example.com",
            api_key="k",
            api_secret="s",
        ),
        sender=sender,
    )
    order = OrderRequest(**{**_order().__dict__, "qty": 0.099})

    ok, order_id, reason = transport.send_order(order)

    assert ok is False
    assert order_id == ""
    assert reason == "invalid_order_request:qty_below_min"
    assert order_requests == 0


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


def test_rest_transport_uses_configured_exchange_info_path() -> None:
    seen_urls: list[str] = []

    def sender(req: Request, __: float) -> str:
        seen_urls.append(req.full_url)
        if req.full_url.endswith("/fapi/v1/exchangeInfo?symbol=BTCUSDT"):
            return json.dumps(
                {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                                {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                            ],
                        }
                    ]
                },
                ensure_ascii=True,
            )
        return json.dumps({"orderId": "12345", "status": "NEW"}, ensure_ascii=True)

    t = BinanceRestTransport(
        RestClientConfig(
            base_url="https://example.com",
            order_path="/fapi/v1/order",
            exchange_info_path="/fapi/v1/exchangeInfo",
            api_key="k",
            api_secret="s",
        ),
        sender=sender,
    )

    ok, _, _ = t.send_order(_order())

    assert ok is True
    assert "https://example.com/fapi/v1/exchangeInfo?symbol=BTCUSDT" in seen_urls


def test_rest_transport_fetches_futures_account_positions() -> None:
    seen: dict[str, object] = {}

    def sender(req: Request, __: float) -> str:
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        return json.dumps(
            {
                "positions": [
                    {
                        "symbol": "BTCUSDT",
                        "positionSide": "BOTH",
                        "positionAmt": "0.0010",
                        "entryPrice": "64207.2",
                        "markPrice": "64540.0",
                        "unrealizedProfit": "0.3328",
                        "leverage": "3",
                        "marginType": "cross",
                        "updateTime": 1781424000162,
                    },
                    {
                        "symbol": "SOLUSDT",
                        "positionSide": "BOTH",
                        "positionAmt": "0.0",
                        "entryPrice": "68.0",
                        "markPrice": "68.2",
                        "unrealizedProfit": "0.0",
                        "leverage": "3",
                        "marginType": "cross",
                        "updateTime": 1781424000162,
                    },
                ]
            },
            ensure_ascii=True,
        )

    transport = BinanceRestTransport(
        RestClientConfig(
            base_url="https://example.com",
            account_path="/fapi/v2/account",
            api_key="k",
            api_secret="s",
        ),
        sender=sender,
    )

    rows, reason = transport.fetch_account_positions()

    assert reason == "ok"
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["position_amt"] == 0.001
    assert rows[0]["qty"] == 0.001
    assert rows[0]["side"] == "buy"
    assert rows[0]["update_at"] == "2026-06-14T08:00:00.162000+00:00"
    assert str(seen["url"]).startswith("https://example.com/fapi/v2/account?timestamp=")
    assert "signature=" in str(seen["url"])
    headers = seen["headers"]
    assert isinstance(headers, dict)
    assert headers.get("X-mbx-apikey") == "k"


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
