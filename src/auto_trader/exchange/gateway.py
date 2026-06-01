from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from auto_trader.exchange.errors import ErrorCode, gateway_error_from_code
from auto_trader.exchange.models import OrderEvent, OrderRequest, now_utc
from auto_trader.stateio import FileLock, atomic_write_json, read_json_with_recovery


class ExchangeTransport(Protocol):
    def send_order(self, order: OrderRequest) -> tuple[bool, str, str]:
        """Returns (ok, order_id, reason)."""


@dataclass(frozen=True)
class GatewayConfig:
    max_retries: int = 3
    reconnect_backoff_ms: int = 200
    stale_signal_ttl_sec: int = 15
    runtime_state_path: str | None = None
    backoff_base_sec: float = 0.2
    max_backoff_sec: float = 5.0
    state_path: str | None = None
    state_lock_timeout_sec: float = 1.0


class OrderGateway:
    def __init__(
        self,
        transport: ExchangeTransport,
        config: GatewayConfig | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.transport = transport
        self.config = config or GatewayConfig()
        self._seen_client_ids: set[str] = set()
        self._pending_orders: dict[str, dict[str, object]] = {}
        self._connected = True
        self._sleep = sleeper or time.sleep
        self._state_path = Path(self.config.state_path) if self.config.state_path else None
        self._load_state()

    def set_connected(self, connected: bool) -> None:
        self._connected = connected

    def submit(self, req: OrderRequest) -> OrderEvent:
        requested_at = now_utc()
        runtime_block_reason = _runtime_gate_reason(self.config.runtime_state_path)
        if runtime_block_reason is not None:
            return _event(
                req=req,
                order_id="",
                status="rejected",
                reason=runtime_block_reason.value,
                requested_at=requested_at,
            )
        if req.client_order_id in self._seen_client_ids:
            return _event(
                req=req,
                order_id="",
                status="rejected",
                reason=ErrorCode.DUPLICATE_CLIENT_ORDER_ID.value,
                requested_at=requested_at,
            )
        if _is_stale(req.signal_ts, requested_at, self.config.stale_signal_ttl_sec):
            return _event(
                req=req,
                order_id="",
                status="rejected",
                reason=ErrorCode.STALE_SIGNAL.value,
                requested_at=requested_at,
            )
        if req.regime == "HIGH_VOL" or (not req.pass_filter):
            return _event(
                req=req,
                order_id="",
                status="rejected",
                reason=ErrorCode.GATING_BLOCKED.value,
                requested_at=requested_at,
            )

        self._seen_client_ids.add(req.client_order_id)
        self._pending_orders[req.client_order_id] = {
            "symbol": req.symbol,
            "side": req.side,
            "qty": req.qty,
            "status": "pending_submit",
            "updated_at": requested_at.isoformat(),
        }
        self._persist_state()
        sent_at: datetime | None = None
        ack_at: datetime | None = None
        last_error = ErrorCode.UNKNOWN_ERROR
        last_reason = ""
        order_id = ""

        for attempt in range(self.config.max_retries + 1):
            if not self._connected:
                self._reconnect()
            sent_at = now_utc()
            ok, remote_order_id, reason = self.transport.send_order(req)
            err = _classify_reason(reason)
            last_error = err
            last_reason = reason
            self._pending_orders[req.client_order_id] = {
                "symbol": req.symbol,
                "side": req.side,
                "qty": req.qty,
                "status": "retrying" if not ok else "ack",
                "last_error": err.value if not ok else "",
                "updated_at": now_utc().isoformat(),
            }
            self._persist_state()
            if ok:
                order_id = remote_order_id
                ack_at = now_utc()
                self._pending_orders.pop(req.client_order_id, None)
                self._persist_state()
                return _event(
                    req=req,
                    order_id=order_id,
                    status="ack",
                    reason=err.value if err != ErrorCode.UNKNOWN_ERROR else reason,
                    requested_at=requested_at,
                    sent_at=sent_at,
                    ack_at=ack_at,
                )
            if attempt < self.config.max_retries and _retryable(err):
                wait_sec = _wait_seconds(
                    reason=reason,
                    attempt=attempt,
                    base=self.config.backoff_base_sec,
                    max_wait=self.config.max_backoff_sec,
                )
                self._sleep(wait_sec)
                continue
            break
        self._pending_orders[req.client_order_id] = {
            "symbol": req.symbol,
            "side": req.side,
            "qty": req.qty,
            "status": "retry_exhausted",
            "last_error": last_error.value,
            "updated_at": now_utc().isoformat(),
        }
        self._persist_state()
        return _event(
            req=req,
            order_id=order_id,
            status="rejected",
            reason=f"retry_exhausted:{last_error.value}"
            if _retryable(last_error)
            else (last_reason or last_error.value),
            requested_at=requested_at,
            sent_at=sent_at,
        )

    def apply_fill_update(self, event: OrderEvent, fill_ratio: float) -> OrderEvent:
        if fill_ratio <= 0.0:
            return event
        if fill_ratio < 1.0:
            return OrderEvent(
                **{**event.__dict__, "status": "partial_filled", "reason": "partial_fill_update"}
            )
        return OrderEvent(
            **{
                **event.__dict__,
                "status": "filled",
                "reason": "fill_update",
                "filled_at": now_utc(),
            }
        )

    def _reconnect(self) -> None:
        # Simulated reconnect in local implementation.
        self._connected = True

    def _load_state(self) -> None:
        if self._state_path is None:
            return
        lock_path = self._state_path.with_suffix(f"{self._state_path.suffix}.lock")
        with FileLock(lock_path, timeout_sec=self.config.state_lock_timeout_sec):
            payload = read_json_with_recovery(self._state_path)
        seen = payload.get("seen_client_ids", [])
        pending = payload.get("pending_orders", {})
        if isinstance(seen, list):
            self._seen_client_ids = {str(v) for v in seen}
        if isinstance(pending, dict):
            self._pending_orders = {str(k): v for k, v in pending.items() if isinstance(v, dict)}

    def _persist_state(self) -> None:
        if self._state_path is None:
            return
        lock_path = self._state_path.with_suffix(f"{self._state_path.suffix}.lock")
        payload: dict[str, object] = {
            "seen_client_ids": sorted(self._seen_client_ids),
            "pending_orders": self._pending_orders,
            "updated_at": now_utc().isoformat(),
        }
        with FileLock(lock_path, timeout_sec=self.config.state_lock_timeout_sec):
            atomic_write_json(self._state_path, payload)


def _is_stale(signal_ts: datetime, now: datetime, ttl_sec: int) -> bool:
    return now - signal_ts > timedelta(seconds=ttl_sec)


def _runtime_gate_reason(runtime_state_path: str | None) -> ErrorCode | None:
    if not runtime_state_path:
        return None
    path = Path(runtime_state_path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ErrorCode.RUNTIME_STATE_INVALID
    trading_enabled = bool(payload.get("trading_enabled", False))
    emergency_stop = bool(payload.get("emergency_stop", False))
    if emergency_stop:
        return ErrorCode.RUNTIME_EMERGENCY_STOP
    if not trading_enabled:
        return ErrorCode.RUNTIME_TRADING_DISABLED
    return None


def _classify_reason(reason: str) -> ErrorCode:
    r = reason.lower()
    if "rate_limit" in r or "429" in r or "418" in r:
        return ErrorCode.RATE_LIMIT
    if "timeout" in r:
        return ErrorCode.TIMEOUT
    if "network" in r:
        return ErrorCode.NETWORK_ERROR
    if "5xx" in r or "server_error" in r or "http_error:5" in r:
        return ErrorCode.SERVER_ERROR
    if r.startswith("accepted"):
        return ErrorCode.UNKNOWN_ERROR
    return ErrorCode.UNKNOWN_ERROR


def classify_error(reason: str) -> tuple[ErrorCode, Exception]:
    code = _classify_reason(reason)
    return code, gateway_error_from_code(code, reason)


def _retryable(code: ErrorCode) -> bool:
    retryable = {
        ErrorCode.RATE_LIMIT,
        ErrorCode.NETWORK_ERROR,
        ErrorCode.TIMEOUT,
        ErrorCode.SERVER_ERROR,
    }
    return code in retryable


def _wait_seconds(*, reason: str, attempt: int, base: float, max_wait: float) -> float:
    retry_after = _parse_retry_after(reason)
    if retry_after is not None:
        return min(retry_after, max_wait)
    exp = base * (2**attempt)
    jitter = float(random.uniform(0.0, base))
    return float(min(exp + jitter, max_wait))


def _parse_retry_after(reason: str) -> float | None:
    # expected sample: "rate_limit:retry_after=2.5"
    key = "retry_after="
    if key not in reason:
        return None
    raw = reason.split(key, 1)[1]
    try:
        return float(raw)
    except ValueError:
        return None


def _event(
    *,
    req: OrderRequest,
    order_id: str,
    status: str,
    reason: str,
    requested_at: datetime,
    sent_at: datetime | None = None,
    ack_at: datetime | None = None,
) -> OrderEvent:
    latency_ms = None
    if sent_at and ack_at:
        latency_ms = int((ack_at - sent_at).total_seconds() * 1000)
    return OrderEvent(
        order_id=order_id,
        client_order_id=req.client_order_id,
        symbol=req.symbol,
        side=req.side,
        qty=req.qty,
        status=status,  # type: ignore[arg-type]
        reason=reason,
        requested_at=requested_at,
        sent_at=sent_at,
        ack_at=ack_at,
        filled_at=None,
        latency_ms=latency_ms,
    )
