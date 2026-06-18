from __future__ import annotations

import json
from datetime import UTC, datetime
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request

from pytest import MonkeyPatch

from auto_trader.exchange.models import OrderRequest
from auto_trader.exchange.rest_client import (
    BinanceRestTransport,
    RestClientConfig,
    SymbolPrecision,
    _as_positive_float,
    _floor_to_step,
    _http_error_detail,
    _normalize_price,
    _normalize_quantity,
    _parse_symbol_precision,
    _sync_timestamp_offset_ms,
    _to_float,
)


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


def test_fetch_account_positions_no_credentials() -> None:
    t = BinanceRestTransport(RestClientConfig(api_key="", api_secret=""))
    rows, reason = t.fetch_account_positions()
    assert rows == []
    assert reason == "credentials_missing"


def test_fetch_account_positions_network_error() -> None:
    def sender(req: Request, timeout: float) -> str:
        raise URLError("network down")

    t = BinanceRestTransport(
        RestClientConfig(api_key="k", api_secret="s"), sender=sender
    )
    rows, reason = t.fetch_account_positions()
    assert rows == []
    assert reason == "network_error"


def test_fetch_account_positions_timeout() -> None:
    def sender(req: Request, timeout: float) -> str:
        raise TimeoutError("timed out")

    t = BinanceRestTransport(
        RestClientConfig(api_key="k", api_secret="s"), sender=sender
    )
    rows, reason = t.fetch_account_positions()
    assert rows == []
    assert reason == "timeout"


def test_fetch_account_positions_rest_error() -> None:
    def sender(req: Request, timeout: float) -> str:
        raise RuntimeError("unexpected")

    t = BinanceRestTransport(
        RestClientConfig(api_key="k", api_secret="s"), sender=sender
    )
    rows, reason = t.fetch_account_positions()
    assert rows == []
    assert reason == "rest_error"


def test_fetch_account_positions_invalid_json() -> None:
    def sender(req: Request, timeout: float) -> str:
        return "not json"

    t = BinanceRestTransport(
        RestClientConfig(api_key="k", api_secret="s"), sender=sender
    )
    rows, reason = t.fetch_account_positions()
    assert rows == []
    assert reason == "invalid_response"


def test_fetch_account_positions_not_dict() -> None:
    def sender(req: Request, timeout: float) -> str:
        return json.dumps([1, 2])

    t = BinanceRestTransport(
        RestClientConfig(api_key="k", api_secret="s"), sender=sender
    )
    rows, reason = t.fetch_account_positions()
    assert rows == []
    assert reason == "invalid_response"


def test_fetch_account_positions_positions_not_list() -> None:
    def sender(req: Request, timeout: float) -> str:
        return json.dumps({"positions": "not_a_list"})

    t = BinanceRestTransport(
        RestClientConfig(api_key="k", api_secret="s"), sender=sender
    )
    rows, reason = t.fetch_account_positions()
    assert rows == []
    assert reason == "invalid_response"


def test_fetch_account_positions_http_error() -> None:
    def sender(req: Request, timeout: float) -> str:
        raise HTTPError(
            url="https://example.com",
            code=403,
            msg="Forbidden",
            hdrs=Message(),
            fp=BytesIO(b""),
        )

    t = BinanceRestTransport(
        RestClientConfig(api_key="k", api_secret="s"), sender=sender
    )
    rows, reason = t.fetch_account_positions()
    assert rows == []
    assert "http_error:403" in reason


def test_fetch_account_positions_sell_side() -> None:
    def sender(req: Request, timeout: float) -> str:
        return json.dumps(
            {
                "positions": [
                    {
                        "symbol": "ETHUSDT",
                        "positionSide": "BOTH",
                        "positionAmt": "-0.5",
                        "entryPrice": "3000.0",
                        "markPrice": "2900.0",
                        "unrealizedProfit": "-50.0",
                        "leverage": "2",
                        "marginType": "isolated",
                        "updateTime": 0,
                    }
                ]
            }
        )

    t = BinanceRestTransport(
        RestClientConfig(api_key="k", api_secret="s"), sender=sender
    )
    rows, reason = t.fetch_account_positions()
    assert reason == "ok"
    assert len(rows) == 1
    assert rows[0]["side"] == "sell"
    assert rows[0]["qty"] == 0.5
    assert rows[0]["update_at"] == ""


def test_send_order_timeout() -> None:
    def sender(req: Request, timeout: float) -> str:
        raise TimeoutError("timed out")

    t = BinanceRestTransport(
        RestClientConfig(api_key="k", api_secret="s"), sender=sender
    )
    ok, order_id, reason = t.send_order(_order())
    assert ok is False
    assert reason == "timeout"


def test_send_order_rest_error() -> None:
    def sender(req: Request, timeout: float) -> str:
        raise RuntimeError("unexpected")

    t = BinanceRestTransport(
        RestClientConfig(api_key="k", api_secret="s"), sender=sender
    )
    ok, order_id, reason = t.send_order(_order())
    assert ok is False
    assert reason == "rest_error"


def test_send_order_invalid_response_json() -> None:
    def sender(req: Request, timeout: float) -> str:
        return "not json"

    t = BinanceRestTransport(
        RestClientConfig(api_key="k", api_secret="s"), sender=sender
    )
    ok, order_id, reason = t.send_order(_order())
    assert ok is False
    assert reason == "invalid_response"


def test_send_order_rejected_no_order_id() -> None:
    def sender(req: Request, timeout: float) -> str:
        return json.dumps({"status": "REJECTED"})

    t = BinanceRestTransport(
        RestClientConfig(api_key="k", api_secret="s"), sender=sender
    )
    ok, order_id, reason = t.send_order(_order())
    assert ok is False
    assert order_id == ""
    assert "rejected" in reason.lower()


def test_sync_timestamp_offset_ms_success() -> None:
    def sender(req: Request, timeout: float) -> str:
        return json.dumps({"serverTime": 200000})

    config = RestClientConfig(time_path="/api/v3/time")
    offset = _sync_timestamp_offset_ms(config, sender)
    assert isinstance(offset, int)


def test_sync_timestamp_offset_ms_failure() -> None:
    def sender(req: Request, timeout: float) -> str:
        raise URLError("fail")

    config = RestClientConfig(time_path="/api/v3/time")
    offset = _sync_timestamp_offset_ms(config, sender)
    assert offset == 0


def test_sync_timestamp_offset_ms_invalid_server_time() -> None:
    def sender(req: Request, timeout: float) -> str:
        return json.dumps({"serverTime": 0})

    config = RestClientConfig(time_path="/api/v3/time")
    offset = _sync_timestamp_offset_ms(config, sender)
    assert offset == 0


def test_floor_to_step_basic() -> None:
    assert _floor_to_step(0.123, 0.01) == 0.12
    assert _floor_to_step(100.99, 0.5) == 100.5
    assert _floor_to_step(5.0, 0.0) == 5.0


def test_normalize_quantity_with_step() -> None:
    prec = SymbolPrecision(step_size=0.01)
    assert _normalize_quantity(0.999, prec) == 0.99


def test_normalize_quantity_no_step() -> None:
    prec = SymbolPrecision()
    assert _normalize_quantity(0.999, prec) == 0.999


def test_normalize_price_none() -> None:
    assert _normalize_price(None, SymbolPrecision()) is None


def test_normalize_price_with_tick() -> None:
    prec = SymbolPrecision(tick_size=0.1)
    assert _normalize_price(100.99, prec) == 100.9


def test_as_positive_float_returns_none_for_bool() -> None:
    assert _as_positive_float(True) is None
    assert _as_positive_float(False) is None


def test_as_positive_float_returns_none_for_zero() -> None:
    assert _as_positive_float(0.0) is None
    assert _as_positive_float(0) is None


def test_as_positive_float_returns_none_for_negative() -> None:
    assert _as_positive_float(-1.0) is None


def test_as_positive_float_returns_value_for_positive() -> None:
    assert _as_positive_float(1.5) == 1.5
    assert _as_positive_float("2.5") == 2.5


def test_as_positive_float_returns_none_for_invalid_str() -> None:
    assert _as_positive_float("abc") is None


def test_as_positive_float_returns_none_for_non_numeric() -> None:
    assert _as_positive_float([1]) is None


def test_to_float_handles_types() -> None:
    assert _to_float(True) == 0.0
    assert _to_float(42) == 42.0
    assert _to_float(3.14) == 3.14
    assert _to_float("1.5") == 1.5
    assert _to_float("abc") == 0.0
    assert _to_float(None) == 0.0
    assert _to_float([]) == 0.0


def test_parse_symbol_precision_extracts_filters() -> None:
    item = {
        "symbol": "BTCUSDT",
        "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
            {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
        ],
    }
    prec = _parse_symbol_precision(item)
    assert prec.tick_size == 0.01
    assert prec.step_size == 0.001
    assert prec.min_qty == 0.001


def test_parse_symbol_precision_empty_filters() -> None:
    prec = _parse_symbol_precision({"symbol": "X", "filters": []})
    assert prec.tick_size is None
    assert prec.step_size is None


def test_parse_symbol_precision_no_filters_key() -> None:
    prec = _parse_symbol_precision({"symbol": "X"})
    assert prec == SymbolPrecision()


def test_http_error_detail_with_json_body() -> None:
    exc = HTTPError(
        url="https://test",
        code=400,
        msg="Bad",
        hdrs=Message(),
        fp=BytesIO(b'{"code": -1000, "msg": "bad request"}'),
    )
    detail = _http_error_detail(exc)
    assert "http_error:400" in detail
    assert "code=-1000" in detail
    assert "msg=bad request" in detail


def test_http_error_detail_with_non_json_body() -> None:
    exc = HTTPError(
        url="https://test",
        code=500,
        msg="Server",
        hdrs=Message(),
        fp=BytesIO(b"plain text error"),
    )
    detail = _http_error_detail(exc)
    assert "http_error:500" in detail
    assert "plain text error" in detail


def test_http_error_detail_with_empty_body() -> None:
    exc = HTTPError(
        url="https://test",
        code=503,
        msg="Unavailable",
        hdrs=Message(),
        fp=BytesIO(b""),
    )
    detail = _http_error_detail(exc)
    assert detail == "http_error:503"


def test_sync_server_time_on_init(monkeypatch: MonkeyPatch) -> None:
    def sender(req: Request, timeout: float) -> str:
        if "/api/v3/time" in req.full_url:
            return json.dumps({"serverTime": 200000})
        return json.dumps({"orderId": "1", "status": "NEW"})

    monkeypatch.setattr("auto_trader.exchange.rest_client.time.time", lambda: 0.1)
    t = BinanceRestTransport(
        RestClientConfig(
            api_key="k",
            api_secret="s",
            sync_server_time=True,
        ),
        sender=sender,
    )
    assert t._timestamp_offset_ms != 0
