from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
OrderStatus = Literal["created", "sent", "ack", "partial_filled", "filled", "rejected", "canceled"]


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    qty: float
    signal_ts: datetime
    regime: str
    pass_filter: bool
    client_order_id: str
    order_type: OrderType = "market"
    limit_price: float | None = None


@dataclass(frozen=True)
class OrderEvent:
    order_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    qty: float
    status: OrderStatus
    reason: str
    requested_at: datetime
    sent_at: datetime | None
    ack_at: datetime | None
    filled_at: datetime | None
    latency_ms: int | None


def now_utc() -> datetime:
    return datetime.now(UTC)
