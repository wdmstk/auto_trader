from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast
from urllib.error import URLError
from urllib.request import Request, urlopen

from auto_trader.exchange.models import OrderRequest

HttpSender = Callable[[Request, float], str]


@dataclass(frozen=True)
class RestClientConfig:
    base_url: str = "https://api.binance.com"
    timeout_sec: float = 5.0


class BinanceRestTransport:
    def __init__(
        self,
        config: RestClientConfig | None = None,
        sender: HttpSender | None = None,
    ) -> None:
        self.config = config or RestClientConfig()
        self._sender = sender or _default_sender

    def send_order(self, order: OrderRequest) -> tuple[bool, str, str]:
        endpoint = self.config.base_url.rstrip("/") + "/api/v3/order"
        payload = {
            "symbol": order.symbol,
            "side": order.side.upper(),
            "type": "MARKET",
            "quantity": order.qty,
            "newClientOrderId": order.client_order_id,
        }
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        req = Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            raw = self._sender(req, self.config.timeout_sec)
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
