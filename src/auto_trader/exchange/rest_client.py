from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from auto_trader.exchange.models import OrderRequest

HttpSender = Callable[[Request, float], str]


@dataclass(frozen=True)
class RestClientConfig:
    base_url: str = "https://api.binance.com"
    order_path: str = "/api/v3/order"
    time_path: str = "/api/v3/time"
    api_key: str = ""
    api_secret: str = ""
    timeout_sec: float = 5.0
    recv_window_ms: int = 5000
    timestamp_offset_ms: int = 0
    sync_server_time: bool = False


class BinanceRestTransport:
    def __init__(
        self,
        config: RestClientConfig | None = None,
        sender: HttpSender | None = None,
    ) -> None:
        self.config = config or RestClientConfig()
        self._sender = sender or _default_sender
        self._timestamp_offset_ms = self.config.timestamp_offset_ms
        if self.config.sync_server_time:
            self._timestamp_offset_ms = _sync_timestamp_offset_ms(self.config, self._sender)

    def send_order(self, order: OrderRequest) -> tuple[bool, str, str]:
        if not self.config.api_key or not self.config.api_secret:
            return False, "", "credentials_missing"
        order_type = order.order_type.upper()
        if order_type == "LIMIT" and order.limit_price is None:
            return False, "", "invalid_order_request:limit_price_required"
        endpoint = self.config.base_url.rstrip("/") + self.config.order_path
        params = {
            "symbol": order.symbol,
            "side": order.side.upper(),
            "type": order_type,
            "quantity": order.qty,
            "newClientOrderId": order.client_order_id,
            "timestamp": int(time.time() * 1000) + self._timestamp_offset_ms,
            "recvWindow": self.config.recv_window_ms,
        }
        if order_type == "LIMIT":
            # Unfilled policy v1: cancel-fixed via IOC.
            params["timeInForce"] = "IOC"
            params["price"] = order.limit_price
        query = urlencode(params, doseq=False)
        signature = hmac.new(
            self.config.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        body = f"{query}&signature={signature}".encode()
        req = Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-MBX-APIKEY": self.config.api_key,
            },
            method="POST",
        )
        try:
            raw = self._sender(req, self.config.timeout_sec)
        except HTTPError as exc:
            detail = _http_error_detail(exc)
            return False, "", detail
        except URLError:
            return False, "", "network_error"
        except TimeoutError:
            return False, "", "timeout"
        except Exception:
            return False, "", "rest_error"

        try:
            parsed = json.loads(raw)
        except Exception:
            return False, "", "invalid_response"

        order_id = str(parsed.get("orderId", ""))
        status = str(parsed.get("status", "")).upper()
        if order_id:
            return True, order_id, f"accepted:{status or 'UNKNOWN'}"
        return False, "", f"rejected:{status or 'UNKNOWN'}"


def _default_sender(req: Request, timeout_sec: float) -> str:
    with urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
        body = cast(Any, resp.read()).decode("utf-8")
        return str(body)


def _sync_timestamp_offset_ms(config: RestClientConfig, sender: HttpSender) -> int:
    endpoint = config.base_url.rstrip("/") + config.time_path
    req = Request(endpoint, method="GET")
    try:
        raw = sender(req, config.timeout_sec)
        parsed = json.loads(raw)
        server_time = int(parsed.get("serverTime", 0))
        if server_time <= 0:
            return 0
        local_time = int(time.time() * 1000)
        return server_time - local_time
    except Exception:
        return 0


def _http_error_detail(exc: HTTPError) -> str:
    raw = ""
    try:
        payload = exc.read()
        if payload:
            raw = payload.decode("utf-8", errors="ignore")
    except Exception:
        raw = ""
    if raw:
        try:
            parsed = json.loads(raw)
            code = parsed.get("code", "")
            msg = parsed.get("msg", "")
            if code != "" or msg:
                return f"http_error:{exc.code}:code={code}:msg={msg}"
        except Exception:
            return f"http_error:{exc.code}:{raw[:200]}"
    return f"http_error:{exc.code}"
