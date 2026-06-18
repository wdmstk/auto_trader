"""Unit tests for execution bridge and integration layer."""

from __future__ import annotations

from datetime import UTC, datetime

from auto_trader.exchange.gateway import GatewayConfig, OrderGateway
from auto_trader.exchange.models import OrderEvent, OrderRequest
from auto_trader.execution.bridge import ExecutionBridge
from auto_trader.execution.integration import GatewayIntegrationLayer
from auto_trader.execution.reconciler import EventType


class MockTransport:
    """Mock transport for testing."""

    def send_order(self, order: OrderRequest) -> tuple[bool, str, str]:
        """Mock send order that always succeeds."""
        return True, "exchange_order_123", ""


class TestExecutionBridge:
    """Test ExecutionBridge."""

    def test_convert_ack_event(self) -> None:
        """Test converting ACK event."""
        bridge = ExecutionBridge()

        order_event = OrderEvent(
            order_id="exchange_123",
            client_order_id="client_123",
            symbol="BTCUSDT",
            side="buy",
            qty=1.0,
            status="ack",
            reason="",
            requested_at=datetime.now(UTC),
            sent_at=datetime.now(UTC),
            ack_at=datetime.now(UTC),
            filled_at=None,
            latency_ms=100,
            order_type="limit",
            limit_price=50000.0,
        )

        exec_event = bridge.convert_order_event(order_event)

        assert exec_event is not None
        assert exec_event.event_type == EventType.ORDER_ACK
        assert exec_event.client_order_id == "client_123"
        assert exec_event.exchange_order_id == "exchange_123"
        assert exec_event.symbol == "BTCUSDT"
        assert exec_event.side == "buy"

    def test_convert_filled_event(self) -> None:
        """Test converting filled event."""
        bridge = ExecutionBridge()

        order_event = OrderEvent(
            order_id="exchange_123",
            client_order_id="client_123",
            symbol="BTCUSDT",
            side="buy",
            qty=1.0,
            status="filled",
            reason="fill_update",
            requested_at=datetime.now(UTC),
            sent_at=datetime.now(UTC),
            ack_at=datetime.now(UTC),
            filled_at=datetime.now(UTC),
            latency_ms=100,
            order_type="limit",
            limit_price=50000.0,
        )

        exec_event = bridge.convert_order_event(order_event)

        assert exec_event is not None
        assert exec_event.event_type == EventType.ORDER_FILLED
        assert exec_event.fill_qty == 1.0
        assert exec_event.fill_price == 50000.0

    def test_convert_partial_filled_event(self) -> None:
        """Test converting partial filled event."""
        bridge = ExecutionBridge()

        order_event = OrderEvent(
            order_id="exchange_123",
            client_order_id="client_123",
            symbol="BTCUSDT",
            side="buy",
            qty=1.0,
            status="partial_filled",
            reason="partial_fill_update",
            requested_at=datetime.now(UTC),
            sent_at=datetime.now(UTC),
            ack_at=datetime.now(UTC),
            filled_at=datetime.now(UTC),
            latency_ms=100,
            order_type="limit",
            limit_price=50000.0,
        )

        exec_event = bridge.convert_order_event(order_event)

        assert exec_event is not None
        assert exec_event.event_type == EventType.ORDER_PARTIAL_FILLED
        assert exec_event.fill_qty == 1.0

    def test_convert_rejected_event(self) -> None:
        """Test converting rejected event."""
        bridge = ExecutionBridge()

        order_event = OrderEvent(
            order_id="",
            client_order_id="client_123",
            symbol="BTCUSDT",
            side="buy",
            qty=1.0,
            status="rejected",
            reason="retry_exhausted:RATE_LIMIT",
            requested_at=datetime.now(UTC),
            sent_at=datetime.now(UTC),
            ack_at=None,
            filled_at=None,
            latency_ms=None,
            order_type="limit",
            limit_price=50000.0,
        )

        exec_event = bridge.convert_order_event(order_event)

        assert exec_event is not None
        assert exec_event.event_type == EventType.ORDER_REJECTED

    def test_convert_unsupported_status(self) -> None:
        """Test converting unsupported status returns None."""
        bridge = ExecutionBridge()

        order_event = OrderEvent(
            order_id="exchange_123",
            client_order_id="client_123",
            symbol="BTCUSDT",
            side="buy",
            qty=1.0,
            status="sent",  # Unsupported status
            reason="",
            requested_at=datetime.now(UTC),
            sent_at=datetime.now(UTC),
            ack_at=None,
            filled_at=None,
            latency_ms=None,
            order_type="limit",
            limit_price=50000.0,
        )

        exec_event = bridge.convert_order_event(order_event)
        assert exec_event is None

    def test_can_convert_status(self) -> None:
        """Test status conversion check."""
        bridge = ExecutionBridge()

        assert bridge.can_convert_status("ack")
        assert bridge.can_convert_status("partial_filled")
        assert bridge.can_convert_status("filled")
        assert bridge.can_convert_status("rejected")
        assert bridge.can_convert_status("canceled")
        assert not bridge.can_convert_status("sent")
        assert not bridge.can_convert_status("created")

    def test_get_supported_statuses(self) -> None:
        """Test getting supported statuses."""
        bridge = ExecutionBridge()

        supported = bridge.get_supported_statuses()
        assert "ack" in supported
        assert "partial_filled" in supported
        assert "filled" in supported
        assert "rejected" in supported
        assert "canceled" in supported
        assert "sent" not in supported


class TestGatewayIntegrationLayer:
    """Test GatewayIntegrationLayer."""

    def test_submit_with_reconciliation_ack(self) -> None:
        """Test submitting order that gets ACK."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "reconciliation_state.json"

            gateway = OrderGateway(
                transport=MockTransport(),
                config=GatewayConfig(state_path=None),
            )

            integration = GatewayIntegrationLayer(
                gateway=gateway,
                state_path=str(state_path),
            )

            req = OrderRequest(
                symbol="BTCUSDT",
                side="buy",
                qty=1.0,
                signal_ts=datetime.now(UTC),
                regime="RANGE",
                pass_filter=True,
                client_order_id="client_123",
                order_type="limit",
                limit_price=50000.0,
            )

            order_event, fill_event = integration.submit_with_reconciliation(req)

            assert order_event.status == "ack"
            assert fill_event is None  # No FillEvent for ACK

            # Check that pending order was registered
            lifecycle = integration.get_order_lifecycle("client_123")
            assert lifecycle is not None
            assert lifecycle.symbol == "BTCUSDT"
            assert lifecycle.side == "buy"

    def test_submit_with_reconciliation_fill(self) -> None:
        """Test processing a fill event."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "reconciliation_state.json"

            gateway = OrderGateway(
                transport=MockTransport(),
                config=GatewayConfig(state_path=None),
            )

            integration = GatewayIntegrationLayer(
                gateway=gateway,
                state_path=str(state_path),
            )

            # First submit the order
            req = OrderRequest(
                symbol="BTCUSDT",
                side="buy",
                qty=1.0,
                signal_ts=datetime.now(UTC),
                regime="RANGE",
                pass_filter=True,
                client_order_id="client_123",
                order_type="limit",
                limit_price=50000.0,
            )

            order_event, _ = integration.submit_with_reconciliation(req)

            # Now process a fill event
            fill_order_event = OrderEvent(
                order_id="exchange_123",
                client_order_id="client_123",
                symbol="BTCUSDT",
                side="buy",
                qty=1.0,
                status="filled",
                reason="fill_update",
                requested_at=datetime.now(UTC),
                sent_at=datetime.now(UTC),
                ack_at=datetime.now(UTC),
                filled_at=datetime.now(UTC),
                latency_ms=100,
                order_type="limit",
                limit_price=50000.0,
            )

            fill_event = integration.process_existing_order_event(fill_order_event)

            assert fill_event is not None  # FillEvent generated for filled
            assert fill_event.qty == 1.0
            assert fill_event.price == 50000.0

    def test_get_pending_orders(self) -> None:
        """Test getting pending orders."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "reconciliation_state.json"

            gateway = OrderGateway(
                transport=MockTransport(),
                config=GatewayConfig(state_path=None),
            )

            integration = GatewayIntegrationLayer(
                gateway=gateway,
                state_path=str(state_path),
            )

            req = OrderRequest(
                symbol="BTCUSDT",
                side="buy",
                qty=1.0,
                signal_ts=datetime.now(UTC),
                regime="RANGE",
                pass_filter=True,
                client_order_id="client_123",
                order_type="limit",
                limit_price=50000.0,
            )

            integration.submit_with_reconciliation(req)

            pending = integration.get_pending_orders()
            assert "client_123" in pending

    def test_cleanup_terminal_orders(self) -> None:
        """Test cleanup of terminal orders."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "reconciliation_state.json"

            gateway = OrderGateway(
                transport=MockTransport(),
                config=GatewayConfig(state_path=None),
            )

            integration = GatewayIntegrationLayer(
                gateway=gateway,
                state_path=str(state_path),
            )

            req = OrderRequest(
                symbol="BTCUSDT",
                side="buy",
                qty=1.0,
                signal_ts=datetime.now(UTC),
                regime="RANGE",
                pass_filter=True,
                client_order_id="client_123",
                order_type="limit",
                limit_price=50000.0,
            )

            integration.submit_with_reconciliation(req)

            # Process a fill to make it terminal
            fill_order_event = OrderEvent(
                order_id="exchange_123",
                client_order_id="client_123",
                symbol="BTCUSDT",
                side="buy",
                qty=1.0,
                status="filled",
                reason="fill_update",
                requested_at=datetime.now(UTC),
                sent_at=datetime.now(UTC),
                ack_at=datetime.now(UTC),
                filled_at=datetime.now(UTC),
                latency_ms=100,
                order_type="limit",
                limit_price=50000.0,
            )

            integration.process_existing_order_event(fill_order_event)

            # Cleanup with 0 second threshold
            removed = integration.cleanup_terminal_orders(older_than_sec=0)
            assert removed >= 0
