"""Data models for execution reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from auto_trader.execution.lifecycle import OrderLifecycle

__all__ = ["OrderState", "ReconciliationConfig", "ReconciliationState"]


class OrderState(str, Enum):  # noqa: UP042
    """Order lifecycle states."""

    PENDING_SUBMIT = "PENDING_SUBMIT"
    PENDING_ACK = "PENDING_ACK"
    ACKED = "ACKED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ReconciliationConfig:
    """Configuration for execution reconciliation."""

    reconciliation_interval_sec: int = 30
    position_mismatch_tolerance_pct: float = 0.1
    order_timeout_sec: int = 300
    enable_auto_correction: bool = False
    event_cache_size: int = 10000
    alert_on_mismatch: bool = True


@dataclass
class ReconciliationState:
    """State for execution reconciliation."""

    pending_orders: dict[str, OrderLifecycle] = field(default_factory=dict)
    last_check_at: datetime | None = None
    mismatch_count: int = 0
    last_mismatch_details: dict[str, Any] = field(default_factory=dict)

    def update_check_time(self) -> None:
        """Update the last reconciliation check time."""
        self.last_check_at = datetime.now(UTC)

    def increment_mismatch(self, details: dict[str, Any]) -> None:
        """Increment mismatch counter and record details."""
        self.mismatch_count += 1
        self.last_mismatch_details = details
