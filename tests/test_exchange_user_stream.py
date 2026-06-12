from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast
from urllib.request import Request

from auto_trader.exchange.user_stream import (
    BinanceFuturesUserStreamClient,
    ExecutionEventCollector,
    HttpSender,
    UserStreamConfig,
)


class _FakeWebSocket:
    def __init__(self, messages: list[str]) -> None:
        self._messages = messages

    async def __aenter__(self) -> _FakeWebSocket:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def __aiter__(self) -> _FakeWebSocket:
        self._iter = iter(self._messages)
        return self

    async def __anext__(self) -> str:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def test_user_stream_client_manages_listen_key() -> None:
    seen: list[tuple[str, str]] = []

    def sender(req: Request, __: float) -> str:
        seen.append((str(req.method), req.full_url))
        return json.dumps({"listenKey": "lk_001"}, ensure_ascii=True)

    typed_sender = cast(HttpSender, sender)

    client = BinanceFuturesUserStreamClient(
        UserStreamConfig(
            rest_base_url="https://example.com",
            listen_key_path="/fapi/v1/listenKey",
            api_key="key",
        ),
        sender=typed_sender,
    )

    listen_key = client.create_listen_key()
    client.keepalive_listen_key(listen_key)
    client.close_listen_key(listen_key)

    assert listen_key == "lk_001"
    assert seen == [
        ("POST", "https://example.com/fapi/v1/listenKey"),
        ("PUT", "https://example.com/fapi/v1/listenKey?listenKey=lk_001"),
        ("DELETE", "https://example.com/fapi/v1/listenKey?listenKey=lk_001"),
    ]


def test_execution_event_collector_appends_parseable_messages(tmp_path: Path) -> None:
    calls: list[str] = []

    def sender(req: Request, __: float) -> str:
        calls.append(f"{req.method}:{req.full_url}")
        return json.dumps({"listenKey": "lk_001"}, ensure_ascii=True)

    typed_sender = cast(HttpSender, sender)

    config = UserStreamConfig(
        rest_base_url="https://example.com",
        ws_base_url="wss://example.com/ws",
        listen_key_path="/fapi/v1/listenKey",
        api_key="key",
        output_path=str(tmp_path / "execution_events.jsonl"),
        keepalive_interval_sec=3600.0,
    )
    collector = ExecutionEventCollector(
        config,
        stream_client=BinanceFuturesUserStreamClient(config, sender=typed_sender),
        connector=lambda url: _FakeWebSocket(
            [
                '{"e":"listenKeyExpired"}',
                (
                    '{"e":"ORDER_TRADE_UPDATE","E":1704067200000,'
                    '"o":{"i":12345,"c":"cid_fut_001","s":"BTCUSDT",'
                    '"S":"BUY","X":"FILLED","z":"0.15"}}'
                ),
            ]
        ),
    )

    result = asyncio.run(collector.stream_once(max_messages=1))

    assert result == {"received": 2, "appended": 1, "ignored": 1}
    rows = (tmp_path / "execution_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    assert '"ORDER_TRADE_UPDATE"' in rows[0]
    assert calls == [
        "POST:https://example.com/fapi/v1/listenKey",
        "DELETE:https://example.com/fapi/v1/listenKey?listenKey=lk_001",
    ]
