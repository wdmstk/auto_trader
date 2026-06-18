"""Integration layer between Gateway and ExecutionReconciler."""

from __future__ import annotations

from collections.abc import Callable
from logging import getLogger
from typing import TYPE_CHECKING

from auto_trader.exchange.gateway import OrderGateway
from auto_trader.exchange.models import OrderEvent, OrderRequest
from auto_trader.execution.bridge import ExecutionBridge
from auto_trader.execution.lifecycle import OrderLifecycle
from auto_trader.execution.models import ReconciliationConfig, ReconciliationState
from auto_trader.execution.reconciler import ExecutionReconciler
from auto_trader.position.models import FillEvent as PositionFillEvent

if TYPE_CHECKING:
    pass

logger = getLogger(__name__)


class GatewayIntegrationLayer:
    """
    Integrates Gateway with ExecutionReconciler for accurate position management.

    This layer bridges the gap between Gateway's OrderEvents and the
    ExecutionReconciler's FillEvents, ensuring that positions are only
    updated when actual fills occur, not on ACK.
    """

    def __init__(
        self,
        gateway: OrderGateway,
        config: ReconciliationConfig | None = None,
        fill_event_callback: Callable[[PositionFillEvent], None] | None = None,
        state_path: str | None = None,
    ) -> None:
        """
        Initialize the gateway integration layer.

        Args:
            gateway: The OrderGateway instance
            config: Reconciliation configuration
            fill_event_callback: Callback for generated FillEvents
            state_path: Path for reconciliation state persistence
        """
        self.gateway = gateway
        self.bridge = ExecutionBridge()
        self.reconciler = ExecutionReconciler(
            config=config,
            fill_event_callback=fill_event_callback,
            state_path=state_path,
        )

    def submit_with_reconciliation(
        self,
        req: OrderRequest,
        *,
        allow_runtime_gate: bool = False,
        allow_policy_gate: bool = False,
    ) -> tuple[OrderEvent, PositionFillEvent | None]:
        """
        Submit order through gateway with execution reconciliation.

        Args:
            req: The order request
            allow_runtime_gate: Whether to bypass runtime gate
            allow_policy_gate: Whether to bypass policy gate

        Returns:
            Tuple of (OrderEvent from gateway, FillEvent from reconciler if any)
        """
        # Submit order through gateway
        order_event = self.gateway.submit(
            req,
            allow_runtime_gate=allow_runtime_gate,
            allow_policy_gate=allow_policy_gate,
        )

        # Register pending order if ACK received
        if order_event.status == "ack":
            self.reconciler.register_pending_order(
                client_order_id=order_event.client_order_id,
                symbol=order_event.symbol,
                side=order_event.side,
                order_type=order_event.order_type,
                quantity=order_event.qty,
                price=order_event.limit_price,
            )

        # Convert OrderEvent to ExecutionEvent and process
        exec_event = self.bridge.convert_order_event(order_event)
        fill_event = None

        if exec_event:
            try:
                fill_event = self.reconciler.process_execution_event(exec_event)
                if fill_event:
                    logger.info(f"FillEvent generated for {order_event.client_order_id}: " f"qty={fill_event.qty}, price={fill_event.price}")
            except Exception as e:
                logger.error(f"Failed to process execution event for {order_event.client_order_id}: {e}")
        else:
            logger.debug(f"No ExecutionEvent generated for OrderEvent with status '{order_event.status}'")

        return order_event, fill_event

    def process_existing_order_event(self, order_event: OrderEvent) -> PositionFillEvent | None:
        """
        Process an existing OrderEvent through the reconciler.

        Useful for processing events from other sources (e.g., WebSocket streams).

        Args:
            order_event: The OrderEvent to process

        Returns:
            FillEvent if generated, None otherwise
        """
        exec_event = self.bridge.convert_order_event(order_event)
        if exec_event:
            return self.reconciler.process_execution_event(exec_event)
        return None

    def get_order_lifecycle(self, client_order_id: str) -> OrderLifecycle | None:
        """
        Get the current lifecycle for an order.

        Args:
            client_order_id: The client order ID

        Returns:
            OrderLifecycle if found, None otherwise
        """
        return self.reconciler.get_order_lifecycle(client_order_id)

    def get_pending_orders(self) -> dict[str, OrderLifecycle]:
        """Get all pending orders from the reconciler."""
        return self.reconciler.get_pending_orders()

    def get_reconciliation_state(self) -> ReconciliationState:
        """Get the current reconciliation state."""
        return self.reconciler.get_reconciliation_state()

    def cleanup_terminal_orders(self, older_than_sec: int = 3600) -> int:
        """
        Clean up terminal orders older than specified seconds.

        Args:
            older_than_sec: Age threshold in seconds

        Returns:
            Number of orders cleaned up
        """
        return self.reconciler.cleanup_terminal_orders(older_than_sec)
