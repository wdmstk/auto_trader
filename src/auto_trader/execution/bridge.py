"""Bridge between Gateway OrderEvents and ExecutionReconciler ExecutionEvents."""

from __future__ import annotations

from logging import getLogger

from auto_trader.exchange.models import OrderEvent
from auto_trader.execution.reconciler import EventType, ExecutionEvent

logger = getLogger(__name__)


class ExecutionBridge:
    """Bridges Gateway OrderEvents to ExecutionReconciler ExecutionEvents."""

    def __init__(self) -> None:
        """Initialize the execution bridge."""
        self._status_mapping: dict[str, EventType] = {
            "ack": EventType.ORDER_ACK,
            "partial_filled": EventType.ORDER_PARTIAL_FILLED,
            "filled": EventType.ORDER_FILLED,
            "rejected": EventType.ORDER_REJECTED,
            "canceled": EventType.ORDER_CANCELLED,
        }

    def convert_order_event(self, order_event: OrderEvent) -> ExecutionEvent | None:
        """
        Convert a Gateway OrderEvent to an ExecutionEvent.

        Args:
            order_event: The OrderEvent from Gateway

        Returns:
            ExecutionEvent if conversion successful, None otherwise
        """
        # Map status to event type
        event_type = self._status_mapping.get(order_event.status)
        if event_type is None:
            logger.debug(f"Cannot convert OrderEvent with status '{order_event.status}' " f"to ExecutionEvent")
            return None

        # Extract fill information if available
        fill_qty = 0.0
        fill_price = 0.0
        fill_time = None

        if order_event.status in {"partial_filled", "filled"}:
            # For partial/filled events, use the order quantity as fill quantity
            # In a real implementation, this would come from actual fill data
            fill_qty = order_event.qty
            fill_price = order_event.limit_price if order_event.limit_price else 0.0
            fill_time = order_event.filled_at or order_event.ack_at

        return ExecutionEvent(
            event_type=event_type,
            client_order_id=order_event.client_order_id,
            exchange_order_id=order_event.order_id if order_event.order_id else None,
            symbol=order_event.symbol,
            side=order_event.side,
            order_type=order_event.order_type,
            quantity=order_event.qty,
            price=order_event.limit_price,
            fill_qty=fill_qty,
            fill_price=fill_price,
            fill_time=fill_time,
            timestamp=order_event.ack_at or order_event.sent_at or order_event.requested_at,
        )

    def can_convert_status(self, status: str) -> bool:
        """Check if a status can be converted to an ExecutionEvent."""
        return status in self._status_mapping

    def get_supported_statuses(self) -> set[str]:
        """Get the set of supported OrderEvent statuses."""
        return set(self._status_mapping.keys())
