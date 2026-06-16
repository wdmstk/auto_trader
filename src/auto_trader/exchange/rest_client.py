from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
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
    exchange_info_path: str = "/api/v3/exchangeInfo"
    account_path: str = "/api/v3/account"
    api_key: str = ""
    api_secret: str = ""
    timeout_sec: float = 5.0
    recv_window_ms: int = 5000
    timestamp_offset_ms: int = 0
    sync_server_time: bool = False


@dataclass(frozen=True)
class SymbolPrecision:
    tick_size: float | None = None
    step_size: float | None = None
    min_qty: float | None = None


class BinanceRestTransport:
    def __init__(
        self,
        config: RestClientConfig | None = None,
        sender: HttpSender | None = None,
    ) -> None:
        self.config = config or RestClientConfig()
        self._sender = sender or _default_sender
        self._timestamp_offset_ms = self.config.timestamp_offset_ms
        self._symbol_precisions: dict[str, SymbolPrecision] = {}
        if self.config.sync_server_time:
            self._timestamp_offset_ms = _sync_timestamp_offset_ms(self.config, self._sender)

    def normalize_order_request(self, order: OrderRequest) -> OrderRequest:
        precision = self._symbol_precision(order.symbol)
        qty = _normalize_quantity(order.qty, precision)
        limit_price = _normalize_price(order.limit_price, precision)
        return OrderRequest(
            **{
                **order.__dict__,
                "qty": qty,
                "limit_price": limit_price,
            }
        )

    def send_order(self, order: OrderRequest) -> tuple[bool, str, str]:
        order = self.normalize_order_request(order)
        if not self.config.api_key or not self.config.api_secret:
            return False, "", "credentials_missing"
        precision = self._symbol_precision(order.symbol)
        if precision.min_qty and order.qty < precision.min_qty:
            return False, "", "invalid_order_request:qty_below_min"
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
        req = self._signed_request(endpoint, params=params, method="POST")
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

    def fetch_account_positions(self) -> tuple[list[dict[str, object]], str]:
        if not self.config.api_key or not self.config.api_secret:
            return [], "credentials_missing"
        endpoint = self.config.base_url.rstrip("/") + self.config.account_path
        req = self._signed_request(
            endpoint,
            params={
                "timestamp": int(time.time() * 1000) + self._timestamp_offset_ms,
                "recvWindow": self.config.recv_window_ms,
            },
            method="GET",
        )
        try:
            raw = self._sender(req, self.config.timeout_sec)
        except HTTPError as exc:
            return [], _http_error_detail(exc)
        except URLError:
            return [], "network_error"
        except TimeoutError:
            return [], "timeout"
        except Exception:
            return [], "rest_error"

        try:
            parsed = json.loads(raw)
        except Exception:
            return [], "invalid_response"
        if not isinstance(parsed, dict):
            return [], "invalid_response"

        rows: list[dict[str, object]] = []
        positions = parsed.get("positions", [])
        if not isinstance(positions, list):
            return [], "invalid_response"
        for item in positions:
            if not isinstance(item, dict):
                continue
            position_amt = _to_float(item.get("positionAmt", 0.0))
            if position_amt == 0.0:
                continue
            entry_price = _to_float(item.get("entryPrice", 0.0))
            mark_price = _to_float(item.get("markPrice", 0.0))
            unrealized_profit = _to_float(item.get("unrealizedProfit", 0.0))
            update_time = _safe_int(item.get("updateTime", 0))
            rows.append(
                {
                    "symbol": str(item.get("symbol", "")).strip().upper(),
                    "position_side": str(item.get("positionSide", "")).strip().upper(),
                    "side": "buy" if position_amt > 0.0 else "sell",
                    "position_amt": position_amt,
                    "qty": abs(position_amt),
                    "entry_price": entry_price,
                    "mark_price": mark_price,
                    "unrealized_profit": unrealized_profit,
                    "leverage": _safe_int(item.get("leverage", 0)),
                    "margin_type": str(item.get("marginType", "")).strip().upper(),
                    "update_time": update_time,
                    "update_at": ("" if update_time <= 0 else datetime.fromtimestamp(update_time / 1000, tz=UTC).isoformat()),
                }
            )
        rows.sort(key=lambda row: str(row.get("symbol", "")))
        return rows, "ok"

    def _signed_request(
        self,
        endpoint: str,
        *,
        params: dict[str, object],
        method: str,
    ) -> Request:
        query = urlencode(params, doseq=False)
        signature = hmac.new(
            self.config.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        body = None
        url = endpoint
        headers = {"X-MBX-APIKEY": self.config.api_key}
        if method.upper() == "POST":
            body = f"{query}&signature={signature}".encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            url = f"{endpoint}?{query}&signature={signature}"
        return Request(url, data=body, headers=headers, method=method.upper())

    def _symbol_precision(self, symbol: str) -> SymbolPrecision:
        key = str(symbol).strip().upper()
        cached = self._symbol_precisions.get(key)
        if cached is not None:
            return cached
        precision = _fetch_symbol_precision(
            symbol=key,
            config=self.config,
            sender=self._sender,
        )
        self._symbol_precisions[key] = precision
        return precision


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
        server_time = _safe_int(parsed.get("serverTime", 0))
        if server_time <= 0:
            return 0
        local_time = int(time.time() * 1000)
        return server_time - local_time
    except Exception:
        return 0


def _fetch_symbol_precision(
    *,
    symbol: str,
    config: RestClientConfig,
    sender: HttpSender,
) -> SymbolPrecision:
    endpoint = config.base_url.rstrip("/") + config.exchange_info_path
    req = Request(f"{endpoint}?symbol={symbol}", method="GET")
    try:
        raw = sender(req, config.timeout_sec)
        payload = json.loads(raw)
    except Exception:
        return SymbolPrecision()
    symbols = payload.get("symbols", [])
    if not isinstance(symbols, list):
        return SymbolPrecision()
    for item in symbols:
        if not isinstance(item, dict):
            continue
        if str(item.get("symbol", "")).strip().upper() != symbol:
            continue
        return _parse_symbol_precision(item)
    return SymbolPrecision()


def _parse_symbol_precision(item: dict[str, Any]) -> SymbolPrecision:
    tick_size: float | None = None
    step_size: float | None = None
    min_qty: float | None = None
    filters = item.get("filters", [])
    if isinstance(filters, list):
        for filt in filters:
            if not isinstance(filt, dict):
                continue
            filter_type = str(filt.get("filterType", "")).strip()
            if filter_type == "PRICE_FILTER":
                tick_size = _as_positive_float(filt.get("tickSize"))
            elif filter_type == "LOT_SIZE":
                step_size = _as_positive_float(filt.get("stepSize"))
                min_qty = _as_positive_float(filt.get("minQty"))
    return SymbolPrecision(tick_size=tick_size, step_size=step_size, min_qty=min_qty)


def _normalize_quantity(value: float, precision: SymbolPrecision) -> float:
    qty = float(value)
    if precision.step_size and precision.step_size > 0:
        qty = _floor_to_step(qty, precision.step_size)
    return qty


def _normalize_price(value: float | None, precision: SymbolPrecision) -> float | None:
    if value is None:
        return None
    price = float(value)
    if precision.tick_size and precision.tick_size > 0:
        price = _floor_to_step(price, precision.tick_size)
    return price


def _floor_to_step(value: float, step: float) -> float:
    if step <= 0:
        return float(value)
    value_dec = Decimal(str(value))
    step_dec = Decimal(str(step))
    floored = (value_dec / step_dec).to_integral_value(rounding=ROUND_DOWN) * step_dec
    return float(floored)


def _as_positive_float(value: object) -> float | None:
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, int | float):
            number = float(value)
        elif isinstance(value, str):
            number = float(value)
        else:
            return None
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _to_float(value: object) -> float:
    try:
        if isinstance(value, bool):
            return 0.0
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            return float(value)
        return 0.0
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: object) -> int:
    try:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            return int(value)
        return 0
    except (TypeError, ValueError):
        return 0


def _safe_int(value: object) -> int:
    try:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            return int(value)
        return 0
    except (TypeError, ValueError):
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
