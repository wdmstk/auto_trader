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
    strategy: str = "legacy"
    timeframe: str = "15m"
    route_key: str = ""

    def __post_init__(self) -> None:
        if not self.route_key:
            self.route_key = build_route_key(
                strategy=self.strategy,
                symbol=self.symbol,
                timeframe=self.timeframe,
            )


@dataclass(frozen=True)
class FillEvent:
    symbol: str
    side: Side
    qty: float
    price: float
    filled_at: datetime
    is_add: bool = False
    strategy: str = "legacy"
    timeframe: str = "15m"
    route_key: str = ""

    def __post_init__(self) -> None:
        if not self.route_key:
            object.__setattr__(
                self,
                "route_key",
                build_route_key(
                    strategy=self.strategy,
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                ),
            )


def build_route_key(*, strategy: str, symbol: str, timeframe: str) -> str:
    route = str(strategy).strip() or "legacy"
    sym = str(symbol).strip()
    tf = str(timeframe).strip() or "15m"
    return f"{route}:{sym}:{tf}"


def now_utc() -> datetime:
    return datetime.now(UTC)
