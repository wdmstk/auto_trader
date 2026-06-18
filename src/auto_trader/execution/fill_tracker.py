"""Fill tracking for cumulative quantity and duplicate detection."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class FillEvent:
    """Represents a fill event from the exchange."""

    event_id: str
    client_order_id: str
    exchange_order_id: str
    symbol: str
    side: str
    fill_qty: float
    fill_price: float
    fill_time: datetime
    trade_id: str | None = None
    commission: float = 0.0
    commission_asset: str | None = None

    def __post_init__(self) -> None:
        """Validate fill event data."""
        if self.fill_qty <= 0:
            raise ValueError("fill_qty must be positive")
        if self.fill_price <= 0:
            raise ValueError("fill_price must be positive")


class FillTracker:
    """Tracks cumulative fills and detects duplicate events."""

    def __init__(self, max_cache_size: int = 10000) -> None:
        """Initialize fill tracker."""
        self.max_cache_size = max_cache_size
        self._processed_events: OrderedDict[str, datetime] = OrderedDict()

    def is_duplicate(self, event_id: str) -> bool:
        """Check if event has already been processed."""
        return event_id in self._processed_events

    def mark_processed(self, event_id: str, timestamp: datetime | None = None) -> None:
        """Mark event as processed."""
        if event_id in self._processed_events:
            return

        # Add to cache
        self._processed_events[event_id] = timestamp or datetime.now(UTC)

        # Enforce size limit
        while len(self._processed_events) > self.max_cache_size:
            self._processed_events.popitem(last=False)

    def cleanup_old_events(self, older_than_sec: int = 3600) -> int:
        """Remove events older than specified seconds."""
        cutoff = datetime.now(UTC).timestamp() - older_than_sec
        to_remove = [event_id for event_id, timestamp in self._processed_events.items() if timestamp.timestamp() < cutoff]
        for event_id in to_remove:
            self._processed_events.pop(event_id, None)
        return len(to_remove)

    def processed_count(self) -> int:
        """Get count of processed events."""
        return len(self._processed_events)

    def clear(self) -> None:
        """Clear all processed events."""
        self._processed_events.clear()


class CumulativeFillTracker:
    """Tracks cumulative fills for an order."""

    def __init__(self, order_quantity: float) -> None:
        """Initialize cumulative fill tracker."""
        self.order_quantity = order_quantity
        self.cumulative_qty: float = 0.0
        self.weighted_price_sum: float = 0.0
        self.avg_fill_price: float = 0.0
        self.fills: list[FillEvent] = []

    def add_fill(self, fill: FillEvent) -> tuple[float, float]:
        """Add a fill and return updated cumulative qty and avg price."""
        if fill.fill_qty <= 0:
            raise ValueError("fill_qty must be positive")

        # Update cumulative quantity
        new_cumulative_qty = self.cumulative_qty + fill.fill_qty

        # Check for overfill
        if new_cumulative_qty > self.order_quantity:
            raise ValueError(f"Overfill detected: cumulative {new_cumulative_qty} > order {self.order_quantity}")

        # Update weighted average price
        self.weighted_price_sum += fill.fill_qty * fill.fill_price
        self.avg_fill_price = self.weighted_price_sum / new_cumulative_qty if new_cumulative_qty > 0 else 0.0

        self.cumulative_qty = new_cumulative_qty
        self.fills.append(fill)

        return self.cumulative_qty, self.avg_fill_price

    def is_fully_filled(self) -> bool:
        """Check if order is fully filled."""
        return self.cumulative_qty >= self.order_quantity

    def remaining_qty(self) -> float:
        """Get remaining quantity to be filled."""
        return max(0.0, self.order_quantity - self.cumulative_qty)

    def fill_percentage(self) -> float:
        """Get fill percentage (0-100)."""
        if self.order_quantity <= 0:
            return 0.0
        return (self.cumulative_qty / self.order_quantity) * 100.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "order_quantity": self.order_quantity,
            "cumulative_qty": self.cumulative_qty,
            "avg_fill_price": self.avg_fill_price,
            "remaining_qty": self.remaining_qty(),
            "fill_percentage": self.fill_percentage(),
            "fill_count": len(self.fills),
        }
