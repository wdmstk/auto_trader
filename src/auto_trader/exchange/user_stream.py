from __future__ import annotations

import argparse
import asyncio
import json
import os
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import websockets

from auto_trader.exchange.ws_client import BinanceWsExecutionClient
from auto_trader.stateio import FileLock


class HttpSender(Protocol):
    def __call__(self, req: Request, timeout_sec: float) -> str: ...


class AsyncWebSocket(Protocol):
    async def __aenter__(self) -> AsyncWebSocket: ...
    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...
    def __aiter__(self) -> Any: ...


class WebSocketConnector(Protocol):
    def __call__(self, url: str) -> AsyncWebSocket: ...


@dataclass(frozen=True)
class UserStreamConfig:
    rest_base_url: str = "https://testnet.binancefuture.com"
    ws_base_url: str = "wss://fstream.binancefuture.com/ws"
    listen_key_path: str = "/fapi/v1/listenKey"
    api_key: str = ""
    timeout_sec: float = 5.0
    keepalive_interval_sec: float = 30.0 * 60.0
    reconnect_delay_sec: float = 5.0
    output_path: str = "data/exchange/execution_events.jsonl"


class BinanceFuturesUserStreamClient:
    def __init__(self, config: UserStreamConfig, sender: HttpSender | None = None) -> None:
        self.config = config
        self._sender = sender or _default_sender

    def create_listen_key(self) -> str:
        req = Request(
            self._url(),
            headers={"X-MBX-APIKEY": self.config.api_key},
            method="POST",
        )
        payload = self._request_json(req)
        listen_key = str(payload.get("listenKey", ""))
        if not listen_key:
            raise RuntimeError("listen_key_missing")
        return listen_key

    def keepalive_listen_key(self, listen_key: str) -> None:
        req = Request(
            f"{self._url()}?listenKey={listen_key}",
            headers={"X-MBX-APIKEY": self.config.api_key},
            method="PUT",
        )
        self._request_json(req)

    def close_listen_key(self, listen_key: str) -> None:
        req = Request(
            f"{self._url()}?listenKey={listen_key}",
            headers={"X-MBX-APIKEY": self.config.api_key},
            method="DELETE",
        )
        self._request_json(req)

    def _url(self) -> str:
        return self.config.rest_base_url.rstrip("/") + self.config.listen_key_path

    def _request_json(self, req: Request) -> dict[str, object]:
        try:
            raw = self._sender(req, self.config.timeout_sec)
        except HTTPError as exc:
            raise RuntimeError(f"http_error:{exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("network_error") from exc
        except TimeoutError as exc:
            raise RuntimeError("timeout") from exc
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
        raise RuntimeError("invalid_response")


class ExecutionEventCollector:
    def __init__(
        self,
        config: UserStreamConfig,
        *,
        stream_client: BinanceFuturesUserStreamClient | None = None,
        connector: WebSocketConnector | None = None,
    ) -> None:
        self.config = config
        self.stream_client = stream_client or BinanceFuturesUserStreamClient(config)
        self.parser = BinanceWsExecutionClient()
        self._connector = connector or (lambda url: websockets.connect(url))

    async def stream_once(self, *, max_messages: int | None = None) -> dict[str, int]:
        listen_key = self.stream_client.create_listen_key()
        keepalive_task = asyncio.create_task(self._keepalive_loop(listen_key))
        received = 0
        appended = 0
        ignored = 0
        try:
            async with self._connector(self._stream_url(listen_key)) as websocket:
                async for raw_message in websocket:
                    received += 1
                    raw_text = str(raw_message)
                    if self.parser.parse_message(raw_text) is None:
                        ignored += 1
                        continue
                    self._append_raw_event(raw_text)
                    appended += 1
                    if max_messages is not None and appended >= max_messages:
                        break
        finally:
            keepalive_task.cancel()
            with suppress(asyncio.CancelledError):
                await keepalive_task
            with suppress(Exception):
                self.stream_client.close_listen_key(listen_key)
        return {
            "received": received,
            "appended": appended,
            "ignored": ignored,
        }

    async def stream_forever(self) -> None:
        while True:
            try:
                await self.stream_once()
            except Exception:
                await asyncio.sleep(max(self.config.reconnect_delay_sec, 0.1))

    async def _keepalive_loop(self, listen_key: str) -> None:
        interval = max(self.config.keepalive_interval_sec, 1.0)
        while True:
            await asyncio.sleep(interval)
            self.stream_client.keepalive_listen_key(listen_key)

    def _stream_url(self, listen_key: str) -> str:
        return f"{self.config.ws_base_url.rstrip('/')}/{listen_key}"

    def _append_raw_event(self, raw_message: str) -> None:
        path = Path(self.config.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(f"{path.suffix}.lock")
        with FileLock(lock_path, timeout_sec=1.0):
            with path.open("a", encoding="utf-8") as f:
                f.write(raw_message.rstrip("\n") + "\n")
                f.flush()
                os.fsync(f.fileno())


def _default_sender(req: Request, timeout_sec: float) -> str:
    with urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
        return cast(str, resp.read().decode("utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Binance Futures user data stream collector.")
    p.add_argument(
        "--rest-base-url",
        default=os.getenv("USER_STREAM_REST_BASE_URL", "https://testnet.binancefuture.com"),
    )
    p.add_argument(
        "--ws-base-url",
        default=os.getenv("USER_STREAM_WS_BASE_URL", "wss://fstream.binancefuture.com/ws"),
    )
    p.add_argument(
        "--listen-key-path",
        default=os.getenv("USER_STREAM_LISTEN_KEY_PATH", "/fapi/v1/listenKey"),
    )
    p.add_argument("--api-key", default=os.getenv("BINANCE_FUTURES_TESTNET_API_KEY", ""))
    p.add_argument(
        "--timeout-sec",
        type=float,
        default=float(os.getenv("USER_STREAM_TIMEOUT_SEC", "5")),
    )
    p.add_argument(
        "--keepalive-interval-sec",
        type=float,
        default=float(os.getenv("USER_STREAM_KEEPALIVE_INTERVAL_SEC", str(30 * 60))),
    )
    p.add_argument(
        "--reconnect-delay-sec",
        type=float,
        default=float(os.getenv("USER_STREAM_RECONNECT_DELAY_SEC", "5")),
    )
    p.add_argument(
        "--output-path",
        default=os.getenv("EXECUTION_EVENTS_PATH", "data/exchange/execution_events.jsonl"),
    )
    p.add_argument("--once", action="store_true")
    p.add_argument("--max-messages", type=int, default=None)
    return p


def main() -> int:
    args = _build_parser().parse_args()
    if not args.api_key:
        print("status=error reason=missing_api_key")
        return 1
    config = UserStreamConfig(
        rest_base_url=args.rest_base_url,
        ws_base_url=args.ws_base_url,
        listen_key_path=args.listen_key_path,
        api_key=args.api_key,
        timeout_sec=float(args.timeout_sec),
        keepalive_interval_sec=float(args.keepalive_interval_sec),
        reconnect_delay_sec=float(args.reconnect_delay_sec),
        output_path=args.output_path,
    )
    collector = ExecutionEventCollector(config)
    if args.once:
        result = asyncio.run(collector.stream_once(max_messages=args.max_messages))
        print(json.dumps(result, ensure_ascii=True))
        return 0
    asyncio.run(collector.stream_forever())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
