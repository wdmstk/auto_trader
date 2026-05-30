from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from auto_trader.exchange.models import OrderEvent, OrderRequest, now_utc


class ExchangeTransport(Protocol):
    def send_order(self, order: OrderRequest) -> tuple[bool, str, str]:
        """Returns (ok, order_id, reason)."""


@dataclass(frozen=True)
class GatewayConfig:
    max_retries: int = 3
    reconnect_backoff_ms: int = 200
    stale_signal_ttl_sec: int = 15
    runtime_state_path: str | None = None


class OrderGateway:
    def __init__(self, transport: ExchangeTransport, config: GatewayConfig | None = None) -> None:
        self.transport = transport
        self.config = config or GatewayConfig()
        self._seen_client_ids: set[str] = set()
        self._connected = True

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
                reason=runtime_block_reason,
                requested_at=requested_at,
            )
        if req.client_order_id in self._seen_client_ids:
            return _event(
                req=req,
                order_id="",
                status="rejected",
                reason="duplicate_client_order_id",
                requested_at=requested_at,
            )
        if _is_stale(req.signal_ts, requested_at, self.config.stale_signal_ttl_sec):
            return _event(
                req=req,
                order_id="",
                status="rejected",
                reason="stale_signal",
                requested_at=requested_at,
            )
        if req.regime == "HIGH_VOL" or (not req.pass_filter):
            return _event(
                req=req,
                order_id="",
                status="rejected",
                reason="gating_blocked",
                requested_at=requested_at,
            )

        self._seen_client_ids.add(req.client_order_id)
        sent_at: datetime | None = None
        ack_at: datetime | None = None
        last_reason = "unknown"
        order_id = ""

        for _ in range(self.config.max_retries + 1):
            if not self._connected:
                self._reconnect()
            sent_at = now_utc()
            ok, remote_order_id, reason = self.transport.send_order(req)
            last_reason = reason
            if ok:
                order_id = remote_order_id
                ack_at = now_utc()
                return _event(
                    req=req,
                    order_id=order_id,
                    status="ack",
                    reason=reason,
                    requested_at=requested_at,
                    sent_at=sent_at,
                    ack_at=ack_at,
                )
        return _event(
            req=req,
            order_id=order_id,
            status="rejected",
            reason=f"retry_exhausted:{last_reason}",
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


def _is_stale(signal_ts: datetime, now: datetime, ttl_sec: int) -> bool:
    return now - signal_ts > timedelta(seconds=ttl_sec)


def _runtime_gate_reason(runtime_state_path: str | None) -> str | None:
    if not runtime_state_path:
        return None
    path = Path(runtime_state_path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "runtime_state_invalid"
    trading_enabled = bool(payload.get("trading_enabled", False))
    emergency_stop = bool(payload.get("emergency_stop", False))
    if emergency_stop:
        return "runtime_emergency_stop"
    if not trading_enabled:
        return "runtime_trading_disabled"
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
