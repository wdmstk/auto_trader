from __future__ import annotations

from auto_trader.exchange.ws_client import BinanceWsExecutionClient


def test_parse_message_from_wrapped_stream_payload() -> None:
    raw = (
        '{"stream":"btcusdt@executionReport","data":{"E":1704067200000,'
        '"i":12345,"c":"cid_001","s":"BTCUSDT","S":"BUY","X":"FILLED","z":"0.15"}}'
    )
    client = BinanceWsExecutionClient()
    ev = client.parse_message(raw)
    assert ev is not None
    assert ev.order_id == "12345"
    assert ev.client_order_id == "cid_001"
    assert ev.symbol == "BTCUSDT"
    assert ev.side == "buy"
    assert ev.status == "filled"
    assert abs(ev.filled_qty - 0.15) < 1e-9


def test_parse_message_invalid_returns_none() -> None:
    client = BinanceWsExecutionClient()
    assert client.parse_message("{bad json") is None


def test_parse_message_from_futures_order_trade_update() -> None:
    raw = (
        '{"e":"ORDER_TRADE_UPDATE","E":1704067200000,'
        '"o":{"i":12345,"c":"cid_fut_001","s":"BTCUSDT","S":"SELL","X":"EXPIRED","z":"0.25"}}'
    )
    client = BinanceWsExecutionClient()
    ev = client.parse_message(raw)
    assert ev is not None
    assert ev.order_id == "12345"
    assert ev.client_order_id == "cid_fut_001"
    assert ev.symbol == "BTCUSDT"
    assert ev.side == "sell"
    assert ev.status == "expired"
    assert abs(ev.filled_qty - 0.25) < 1e-9
