from __future__ import annotations

from auto_trader.exchange.ws_client import BinanceWsExecutionClient


def test_parse_message_from_wrapped_stream_payload() -> None:
    raw = (
        '{"stream":"btcusdt@executionReport","data":{"E":1704067200000,'
        '"i":12345,"s":"BTCUSDT","S":"BUY","X":"FILLED","z":"0.15"}}'
    )
    client = BinanceWsExecutionClient()
    ev = client.parse_message(raw)
    assert ev is not None
    assert ev.order_id == "12345"
    assert ev.symbol == "BTCUSDT"
    assert ev.side == "buy"
    assert ev.status == "filled"
    assert abs(ev.filled_qty - 0.15) < 1e-9


def test_parse_message_invalid_returns_none() -> None:
    client = BinanceWsExecutionClient()
    assert client.parse_message("{bad json") is None
