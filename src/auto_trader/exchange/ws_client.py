from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast


@dataclass(frozen=True)
class ExecutionStreamEvent:
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    status: str
    filled_qty: float
    event_ts: datetime


class BinanceWsExecutionClient:
    def parse_message(self, raw_message: str) -> ExecutionStreamEvent | None:
        try:
            data = json.loads(raw_message)
        except Exception:
            return None

        # Supports both wrapped stream payload and direct event payload.
        payload = data.get("data", data) if isinstance(data, dict) else {}
        if not isinstance(payload, dict):
            return None

        order_payload = payload
        event_ms = _to_int(payload.get("E", 0))
        if str(payload.get("e", "")).upper() == "ORDER_TRADE_UPDATE":
            nested = payload.get("o", {})
            if not isinstance(nested, dict):
                return None
            order_payload = nested

        order_id = str(order_payload.get("i", ""))
        client_order_id = str(order_payload.get("c", ""))
        symbol = str(order_payload.get("s", ""))
        side = str(order_payload.get("S", "")).lower()
        status = str(order_payload.get("X", "")).lower()
        qty = _to_float(order_payload.get("z", 0.0))
        if not order_id or not symbol:
            return None
        if event_ms > 0:
            event_ts = datetime.fromtimestamp(event_ms / 1000, tz=UTC)
        else:
            event_ts = datetime.now(UTC)
        return ExecutionStreamEvent(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            status=status,
            filled_qty=qty,
            event_ts=event_ts,
        )


def _to_float(v: object) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _to_int(v: object) -> int:
    try:
        return int(cast(Any, v))
    except (TypeError, ValueError):
        return 0
