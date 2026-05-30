from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

Side = Literal["buy", "sell"]


@dataclass
class PositionState:
    symbol: str
    side: Side
    qty: float
    avg_entry: float
    unrealized_pnl_pct: float
    add_count: int
    updated_at: datetime


@dataclass(frozen=True)
class FillEvent:
    symbol: str
    side: Side
    qty: float
    price: float
    filled_at: datetime
    is_add: bool = False


def now_utc() -> datetime:
    return datetime.now(UTC)
