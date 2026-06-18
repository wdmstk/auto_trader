"""Execution reconciliation service for accurate position management."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from logging import getLogger
from pathlib import Path

from auto_trader.execution.fill_tracker import FillTracker
from auto_trader.execution.lifecycle import OrderLifecycle, OrderState
from auto_trader.execution.models import ReconciliationConfig, ReconciliationState
from auto_trader.position.models import FillEvent as PositionFillEvent
from auto_trader.stateio import atomic_write_json, read_json_with_recovery

logger = getLogger(__name__)


class EventType(str, Enum):  # noqa: UP042
    """Execution event types from exchange."""

    ORDER_ACK = "ORDER_ACK"
    ORDER_PARTIAL_FILLED = "ORDER_PARTIAL_FILLED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_EXPIRED = "ORDER_EXPIRED"
    ORDER_REJECTED = "ORDER_REJECTED"


@dataclass
class ExecutionEvent:
    """Execution event from exchange."""

    event_type: EventType
    client_order_id: str
    exchange_order_id: str | None = None
    symbol: str = ""
    side: str = ""
    order_type: str = ""
    quantity: float = 0.0
    price: float | None = None
    fill_qty: float = 0.0
    fill_price: float = 0.0
    fill_time: datetime | None = None
    trade_id: str | None = None
    timestamp: datetime | None = None
    commission: float = 0.0
    commission_asset: str | None = None


class ExecutionReconciler:
    """Reconciles execution events and generates accurate FillEvents."""

    def __init__(
        self,
        config: ReconciliationConfig | None = None,
        fill_event_callback: Callable[[PositionFillEvent], None] | None = None,
        state_path: str | Path | None = None,
    ) -> None:
        """Initialize execution reconciler."""
        self.config = config or ReconciliationConfig()
        self.state = ReconciliationState()
        self.fill_tracker = FillTracker(max_cache_size=self.config.event_cache_size)
        self.fill_event_callback = fill_event_callback
        self._cumulative_trackers: dict[str, FillTracker] = {}
        self._state_path = Path(state_path) if state_path else None
        if self._state_path:
            self._load_state()

    def process_execution_event(self, event: ExecutionEvent) -> PositionFillEvent | None:
        """Process an execution event and return FillEvent if appropriate."""
        if not event.client_order_id:
            logger.warning("Execution event missing client_order_id")
            return None

        # Check for duplicate events
        event_id = self._generate_event_id(event)
        if self.fill_tracker.is_duplicate(event_id):
            logger.debug(f"Duplicate event detected: {event_id}")
            return None

        self.fill_tracker.mark_processed(event_id, event.timestamp)

        # Get or create order lifecycle
        lifecycle = self.state.pending_orders.get(event.client_order_id)

        # Handle new order submission
        if event.event_type == EventType.ORDER_ACK:
            result = self._handle_order_ack(event, lifecycle)
        # Handle partial fill
        elif event.event_type == EventType.ORDER_PARTIAL_FILLED:
            result = self._handle_partial_fill(event, lifecycle)
        # Handle complete fill
        elif event.event_type == EventType.ORDER_FILLED:
            result = self._handle_complete_fill(event, lifecycle)
        # Handle cancellation
        elif event.event_type == EventType.ORDER_CANCELLED:
            result = self._handle_cancellation(event, lifecycle)
        # Handle expiration
        elif event.event_type == EventType.ORDER_EXPIRED:
            result = self._handle_expiration(event, lifecycle)
        # Handle rejection
        elif event.event_type == EventType.ORDER_REJECTED:
            result = self._handle_rejection(event, lifecycle)
        else:
            logger.warning(f"Unknown event type: {event.event_type}")
            return None

        # Save state after processing
        self.save_state()

        return result

    def register_pending_order(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None,
    ) -> OrderLifecycle:
        """Register a new pending order."""
        lifecycle = OrderLifecycle(
            client_order_id=client_order_id,
            exchange_order_id=None,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            state=OrderState.PENDING_ACK,  # Start in PENDING_ACK since order is being submitted
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.state.pending_orders[client_order_id] = lifecycle
        self.save_state()
        return lifecycle

    def get_order_lifecycle(self, client_order_id: str) -> OrderLifecycle | None:
        """Get order lifecycle by client_order_id."""
        return self.state.pending_orders.get(client_order_id)

    def cleanup_terminal_orders(self, older_than_sec: int = 3600) -> int:
        """Remove terminal orders older than specified seconds."""
        cutoff = datetime.now(UTC).timestamp() - older_than_sec
        to_remove = [
            order_id for order_id, lifecycle in self.state.pending_orders.items() if lifecycle.is_terminal() and lifecycle.updated_at.timestamp() < cutoff
        ]
        for order_id in to_remove:
            self.state.pending_orders.pop(order_id, None)
        return len(to_remove)

    def get_pending_orders(self) -> dict[str, OrderLifecycle]:
        """Get all pending orders."""
        return self.state.pending_orders.copy()

    def get_reconciliation_state(self) -> ReconciliationState:
        """Get current reconciliation state."""
        return self.state

    def _generate_event_id(self, event: ExecutionEvent) -> str:
        """Generate unique event ID."""
        parts = [event.event_type.value, event.client_order_id]
        if event.exchange_order_id:
            parts.append(event.exchange_order_id)
        if event.trade_id:
            parts.append(event.trade_id)
        if event.timestamp:
            parts.append(event.timestamp.isoformat())
        return "|".join(parts)

    def _handle_order_ack(self, event: ExecutionEvent, lifecycle: OrderLifecycle | None) -> PositionFillEvent | None:
        """Handle order acknowledgment."""
        if lifecycle is None:
            logger.warning(f"Order ACK for unknown order: {event.client_order_id}")
            return None

        # Update order with exchange order ID
        lifecycle.exchange_order_id = event.exchange_order_id
        lifecycle.transition_to(OrderState.ACKED, event.timestamp)

        logger.info(f"Order ACK: {event.client_order_id} -> {event.exchange_order_id}")
        return None  # No FillEvent for ACK

    def _handle_partial_fill(self, event: ExecutionEvent, lifecycle: OrderLifecycle | None) -> PositionFillEvent | None:
        """Handle partial fill."""
        if lifecycle is None:
            logger.warning(f"Partial fill for unknown order: {event.client_order_id}")
            return None

        # Update state
        lifecycle.transition_to(OrderState.PARTIALLY_FILLED, event.timestamp)

        # Add fill
        lifecycle.add_fill(event.fill_qty, event.fill_price, event.fill_time or event.timestamp)

        logger.info(f"Partial fill: {event.client_order_id} qty={event.fill_qty} " f"price={event.fill_price} cumulative={lifecycle.cumulative_filled_qty}")

        # No FillEvent for partial fills (only for complete fills)
        return None

    def _handle_complete_fill(self, event: ExecutionEvent, lifecycle: OrderLifecycle | None) -> PositionFillEvent | None:
        """Handle complete fill."""
        if lifecycle is None:
            logger.warning(f"Complete fill for unknown order: {event.client_order_id}")
            return None

        # Update state
        lifecycle.transition_to(OrderState.FILLED, event.fill_time or event.timestamp)

        # Add fill (might be called after partial fills)
        lifecycle.add_fill(event.fill_qty, event.fill_price, event.fill_time or event.timestamp)

        logger.info(f"Complete fill: {event.client_order_id} qty={event.fill_qty} " f"price={event.fill_price} cumulative={lifecycle.cumulative_filled_qty}")

        # Generate FillEvent only for complete fills
        return self._generate_fill_event(lifecycle)

    def _handle_cancellation(self, event: ExecutionEvent, lifecycle: OrderLifecycle | None) -> PositionFillEvent | None:
        """Handle order cancellation."""
        if lifecycle is None:
            logger.warning(f"Cancellation for unknown order: {event.client_order_id}")
            return None

        lifecycle.transition_to(OrderState.CANCELLED, event.timestamp)

        # If partially filled, generate FillEvent for the filled portion
        if lifecycle.cumulative_filled_qty > 0:
            logger.info(f"Order cancelled with partial fill: {event.client_order_id} " f"filled={lifecycle.cumulative_filled_qty}")
            return self._generate_fill_event(lifecycle)

        logger.info(f"Order cancelled: {event.client_order_id}")
        return None

    def _handle_expiration(self, event: ExecutionEvent, lifecycle: OrderLifecycle | None) -> PositionFillEvent | None:
        """Handle order expiration."""
        if lifecycle is None:
            logger.warning(f"Expiration for unknown order: {event.client_order_id}")
            return None

        lifecycle.transition_to(OrderState.EXPIRED, event.timestamp)

        # If partially filled, generate FillEvent for the filled portion
        if lifecycle.cumulative_filled_qty > 0:
            logger.info(f"Order expired with partial fill: {event.client_order_id} " f"filled={lifecycle.cumulative_filled_qty}")
            return self._generate_fill_event(lifecycle)

        logger.info(f"Order expired: {event.client_order_id}")
        return None

    def _handle_rejection(self, event: ExecutionEvent, lifecycle: OrderLifecycle | None) -> PositionFillEvent | None:
        """Handle order rejection."""
        if lifecycle is None:
            logger.warning(f"Rejection for unknown order: {event.client_order_id}")
            return None

        lifecycle.transition_to(OrderState.REJECTED, event.timestamp)

        logger.warning(f"Order rejected: {event.client_order_id}")
        return None

    def _generate_fill_event(self, lifecycle: OrderLifecycle) -> PositionFillEvent:
        """Generate a Position FillEvent from order lifecycle."""
        fill_event = PositionFillEvent(
            symbol=lifecycle.symbol,
            side=lifecycle.side,  # type: ignore
            qty=lifecycle.cumulative_filled_qty,
            price=lifecycle.avg_fill_price,
            filled_at=lifecycle.filled_at or lifecycle.updated_at,
        )

        # Call callback if registered
        if self.fill_event_callback:
            self.fill_event_callback(fill_event)

        return fill_event

    def save_state(self) -> None:
        """Save reconciliation state to disk."""
        if not self._state_path:
            return

        # Convert pending orders to serializable format
        pending_orders_serializable: dict[str, dict[str, object]] = {order_id: lifecycle.to_dict() for order_id, lifecycle in self.state.pending_orders.items()}

        state_data: dict[str, object] = {
            "pending_orders": pending_orders_serializable,
            "last_check_at": self.state.last_check_at.isoformat() if self.state.last_check_at else None,
            "mismatch_count": self.state.mismatch_count,
            "last_mismatch_details": self.state.last_mismatch_details,
        }

        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self._state_path, state_data)

    def _load_state(self) -> None:
        """Load reconciliation state from disk."""
        if not self._state_path or not self._state_path.exists():
            return

        try:
            state_data = read_json_with_recovery(self._state_path)
            if not isinstance(state_data, dict):
                logger.warning(f"Invalid state data in {self._state_path}")
                return

            # Restore pending orders
            pending_orders_data = state_data.get("pending_orders")
            if isinstance(pending_orders_data, dict):
                for order_id, lifecycle_data in pending_orders_data.items():
                    if isinstance(lifecycle_data, dict):
                        try:
                            lifecycle = OrderLifecycle.from_dict(lifecycle_data)
                            self.state.pending_orders[order_id] = lifecycle
                        except Exception as e:
                            logger.warning(f"Failed to restore order {order_id}: {e}")

            # Restore metadata
            last_check_at = state_data.get("last_check_at")
            if isinstance(last_check_at, str):
                try:
                    self.state.last_check_at = datetime.fromisoformat(last_check_at)
                except Exception as e:
                    logger.warning(f"Failed to restore last_check_at: {e}")

            mismatch_count = state_data.get("mismatch_count")
            if isinstance(mismatch_count, int):
                self.state.mismatch_count = mismatch_count

            last_mismatch_details = state_data.get("last_mismatch_details")
            if isinstance(last_mismatch_details, dict):
                self.state.last_mismatch_details = last_mismatch_details

            logger.info(f"Loaded reconciliation state from {self._state_path}")

        except Exception as e:
            logger.warning(f"Failed to load state from {self._state_path}: {e}")
