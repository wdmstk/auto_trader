"""Order lifecycle management for execution reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from auto_trader.execution.models import OrderState

__all__ = ["OrderLifecycle", "OrderState"]


@dataclass
class OrderLifecycle:
    """Represents the complete lifecycle of an order."""

    client_order_id: str
    exchange_order_id: str | None
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float | None
    state: OrderState
    created_at: datetime
    updated_at: datetime
    filled_at: datetime | None = None
    cumulative_filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    processed_events: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Validate order lifecycle data."""
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.side not in {"buy", "sell"}:
            raise ValueError(f"side must be 'buy' or 'sell', got {self.side}")
        if self.price is not None and self.price <= 0:
            raise ValueError("price must be positive if specified")

    def can_transition_to(self, new_state: OrderState) -> bool:
        """Check if state transition is valid."""
        valid_transitions: dict[OrderState, set[OrderState]] = {
            OrderState.PENDING_SUBMIT: {
                OrderState.PENDING_ACK,
                OrderState.REJECTED,
            },
            OrderState.PENDING_ACK: {
                OrderState.ACKED,
                OrderState.REJECTED,
                OrderState.EXPIRED,
                OrderState.FILLED,  # Allow direct transition for instant fills
                OrderState.PARTIALLY_FILLED,  # Allow direct transition for partial fills
            },
            OrderState.ACKED: {
                OrderState.PARTIALLY_FILLED,
                OrderState.FILLED,
                OrderState.CANCELLED,
                OrderState.EXPIRED,
            },
            OrderState.PARTIALLY_FILLED: {
                OrderState.PARTIALLY_FILLED,  # Additional partial fills
                OrderState.FILLED,
                OrderState.CANCELLED,
                OrderState.EXPIRED,
            },
            OrderState.FILLED: set(),  # Terminal state
            OrderState.CANCELLED: set(),  # Terminal state
            OrderState.EXPIRED: set(),  # Terminal state
            OrderState.REJECTED: set(),  # Terminal state
            OrderState.UNKNOWN: {
                OrderState.PENDING_SUBMIT,
                OrderState.ACKED,
                OrderState.PARTIALLY_FILLED,
                OrderState.FILLED,
                OrderState.CANCELLED,
                OrderState.EXPIRED,
                OrderState.REJECTED,
            },
        }
        return new_state in valid_transitions.get(self.state, set())

    def transition_to(self, new_state: OrderState, timestamp: datetime | None = None) -> None:
        """Transition to a new state if valid."""
        if not self.can_transition_to(new_state):
            raise ValueError(f"Invalid state transition: {self.state} -> {new_state}")
        self.state = new_state
        self.updated_at = timestamp or datetime.now(UTC)

    def add_fill(self, fill_qty: float, fill_price: float, timestamp: datetime | None = None) -> None:
        """Add a fill to the order."""
        if fill_qty <= 0:
            raise ValueError("fill_qty must be positive")
        if fill_price <= 0:
            raise ValueError("fill_price must be positive")

        # Update cumulative filled quantity and average price
        total_qty = self.cumulative_filled_qty + fill_qty
        if total_qty > 0:
            weighted_price_sum = self.avg_fill_price * self.cumulative_filled_qty + fill_price * fill_qty
            self.avg_fill_price = weighted_price_sum / total_qty
        else:
            self.avg_fill_price = fill_price

        self.cumulative_filled_qty = total_qty
        self.filled_at = timestamp or datetime.now(UTC)
        self.updated_at = self.filled_at

    def is_fully_filled(self) -> bool:
        """Check if order is fully filled."""
        return self.state == OrderState.FILLED

    def is_partially_filled(self) -> bool:
        """Check if order is partially filled."""
        return self.state == OrderState.PARTIALLY_FILLED

    def is_terminal(self) -> bool:
        """Check if order is in a terminal state."""
        return self.state in {
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.EXPIRED,
            OrderState.REJECTED,
        }

    def is_active(self) -> bool:
        """Check if order is still active."""
        return not self.is_terminal()

    def remaining_qty(self) -> float:
        """Get remaining quantity to be filled."""
        return max(0.0, self.quantity - self.cumulative_filled_qty)

    def fill_percentage(self) -> float:
        """Get fill percentage (0-100)."""
        if self.quantity <= 0:
            return 0.0
        return (self.cumulative_filled_qty / self.quantity) * 100.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "client_order_id": self.client_order_id,
            "exchange_order_id": self.exchange_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "price": self.price,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "cumulative_filled_qty": self.cumulative_filled_qty,
            "avg_fill_price": self.avg_fill_price,
            "processed_events": list(self.processed_events),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrderLifecycle:
        """Create from dictionary."""
        return cls(
            client_order_id=data["client_order_id"],
            exchange_order_id=data.get("exchange_order_id"),
            symbol=data["symbol"],
            side=data["side"],
            order_type=data["order_type"],
            quantity=data["quantity"],
            price=data.get("price"),
            state=OrderState(data["state"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            filled_at=datetime.fromisoformat(data["filled_at"]) if data.get("filled_at") else None,
            cumulative_filled_qty=data.get("cumulative_filled_qty", 0.0),
            avg_fill_price=data.get("avg_fill_price", 0.0),
            processed_events=set(data.get("processed_events", [])),
        )
