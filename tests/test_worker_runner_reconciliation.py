"""Integration tests for ExecutionReconciler in worker runner."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from auto_trader.exchange.ws_client import ExecutionStreamEvent
from auto_trader.worker.runner import LiveTradingWorker, WorkerConfig


class TestExecutionStreamEventConversion:
    """Test ExecutionStreamEvent to OrderEvent conversion."""

    def test_convert_filled_event(self) -> None:
        """Test converting filled execution stream event."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir)

            # Create worker with ExecutionReconciler enabled
            config = WorkerConfig(
                enable_execution_reconciliation=True,
                reconciliation_state_path=str(state_path / "reconciliation_state.json"),
                gateway_state_path=str(state_path / "gateway_state.json"),
                positions_dir=str(state_path / "positions"),
                worker_state_path=str(state_path / "worker_state.json"),
                symbols=("BTCUSDT",),
                trend_symbols=("BTCUSDT",),
                range_symbols=(),
            )

            # Mock transport
            class MockTransport:
                def send_order(self, order: object) -> tuple[bool, str, str]:
                    return True, "exchange_order_123", ""

            worker = LiveTradingWorker(
                config=config,
                transport=MockTransport(),
            )

            # Create execution stream event
            event = ExecutionStreamEvent(
                order_id="exchange_123",
                client_order_id="client_123",
                symbol="BTCUSDT",
                side="buy",
                status="filled",
                filled_qty=1.0,
                avg_fill_price=50000.0,
                event_ts=datetime.now(UTC),
            )

            # Create order row
            order_row = {
                "symbol": "BTCUSDT",
                "side": "buy",
                "qty": 1.0,
                "order_type": "limit",
                "limit_price": 50000.0,
                "route_key": "trend_BTCUSDT_15m",
                "strategy": "trend",
                "timeframe": "15m",
                "action": "add",
            }

            # Convert event
            order_event = worker._convert_execution_stream_to_order_event(event, order_row)

            assert order_event is not None
            assert order_event.order_id == "exchange_123"
            assert order_event.client_order_id == "client_123"
            assert order_event.symbol == "BTCUSDT"
            assert order_event.side == "buy"
            assert order_event.status == "filled"
            assert order_event.filled_at is not None

    def test_convert_partial_filled_event(self) -> None:
        """Test converting partial filled execution stream event."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir)

            config = WorkerConfig(
                enable_execution_reconciliation=True,
                reconciliation_state_path=str(state_path / "reconciliation_state.json"),
                gateway_state_path=str(state_path / "gateway_state.json"),
                positions_dir=str(state_path / "positions"),
                worker_state_path=str(state_path / "worker_state.json"),
                symbols=("BTCUSDT",),
                trend_symbols=("BTCUSDT",),
                range_symbols=(),
            )

            class MockTransport:
                def send_order(self, order: object) -> tuple[bool, str, str]:
                    return True, "exchange_order_123", ""

            worker = LiveTradingWorker(
                config=config,
                transport=MockTransport(),
            )

            event = ExecutionStreamEvent(
                order_id="exchange_123",
                client_order_id="client_123",
                symbol="BTCUSDT",
                side="buy",
                status="partially_filled",
                filled_qty=0.5,
                avg_fill_price=50000.0,
                event_ts=datetime.now(UTC),
            )

            order_row = {
                "symbol": "BTCUSDT",
                "side": "buy",
                "qty": 1.0,
                "order_type": "limit",
                "limit_price": 50000.0,
                "route_key": "trend_BTCUSDT_15m",
                "strategy": "trend",
                "timeframe": "15m",
                "action": "add",
            }

            order_event = worker._convert_execution_stream_to_order_event(event, order_row)

            assert order_event is not None
            assert order_event.status == "partial_filled"
            assert order_event.filled_at is not None

    def test_convert_canceled_event(self) -> None:
        """Test converting canceled execution stream event."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir)

            config = WorkerConfig(
                enable_execution_reconciliation=True,
                reconciliation_state_path=str(state_path / "reconciliation_state.json"),
                gateway_state_path=str(state_path / "gateway_state.json"),
                positions_dir=str(state_path / "positions"),
                worker_state_path=str(state_path / "worker_state.json"),
                symbols=("BTCUSDT",),
                trend_symbols=("BTCUSDT",),
                range_symbols=(),
            )

            class MockTransport:
                def send_order(self, order: object) -> tuple[bool, str, str]:
                    return True, "exchange_order_123", ""

            worker = LiveTradingWorker(
                config=config,
                transport=MockTransport(),
            )

            event = ExecutionStreamEvent(
                order_id="exchange_123",
                client_order_id="client_123",
                symbol="BTCUSDT",
                side="buy",
                status="canceled",
                filled_qty=0.0,
                avg_fill_price=0.0,
                event_ts=datetime.now(UTC),
            )

            order_row = {
                "symbol": "BTCUSDT",
                "side": "buy",
                "qty": 1.0,
                "order_type": "limit",
                "limit_price": 50000.0,
                "route_key": "trend_BTCUSDT_15m",
                "strategy": "trend",
                "timeframe": "15m",
                "action": "add",
            }

            order_event = worker._convert_execution_stream_to_order_event(event, order_row)

            assert order_event is not None
            assert order_event.status == "canceled"
            assert order_event.filled_at is None


class TestExecutionReconcilerAdvancedScenarios:
    """Test advanced reconciliation scenarios."""

    def test_duplicate_event_handling(self) -> None:
        """Test that duplicate events are properly handled."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir)

            config = WorkerConfig(
                enable_execution_reconciliation=True,
                reconciliation_state_path=str(state_path / "reconciliation_state.json"),
                gateway_state_path=str(state_path / "gateway_state.json"),
                positions_dir=str(state_path / "positions"),
                worker_state_path=str(state_path / "worker_state.json"),
                symbols=("BTCUSDT",),
                trend_symbols=("BTCUSDT",),
                range_symbols=(),
            )

            class MockTransport:
                def send_order(self, order: object) -> tuple[bool, str, str]:
                    return True, "exchange_order_123", ""

            worker = LiveTradingWorker(
                config=config,
                transport=MockTransport(),
            )

            assert worker.execution_integration_layer is not None
            worker.execution_integration_layer.reconciler.register_pending_order(
                client_order_id="client_123",
                symbol="BTCUSDT",
                side="buy",
                order_type="limit",
                quantity=1.0,
                price=50000.0,
            )

            # First fill event
            event = ExecutionStreamEvent(
                order_id="exchange_123",
                client_order_id="client_123",
                symbol="BTCUSDT",
                side="buy",
                status="filled",
                filled_qty=1.0,
                avg_fill_price=50000.0,
                event_ts=datetime.now(UTC),
            )

            order_row = {
                "symbol": "BTCUSDT",
                "side": "buy",
                "qty": 1.0,
                "order_type": "limit",
                "limit_price": 50000.0,
                "route_key": "trend_BTCUSDT_15m",
                "strategy": "trend",
                "timeframe": "15m",
                "action": "add",
            }

            order_event = worker._convert_execution_stream_to_order_event(event, order_row)
            assert worker.execution_integration_layer is not None
            fill_event1 = worker.execution_integration_layer.process_existing_order_event(order_event)
            assert fill_event1 is not None

            # Duplicate event (same event, should be ignored)
            fill_event2 = worker.execution_integration_layer.process_existing_order_event(order_event)
            # Duplicate should not generate another FillEvent
            assert fill_event2 is None

    def test_restart_recovery(self) -> None:
        """Test state recovery after restart."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir)
            recon_state_path = str(state_path / "reconciliation_state.json")

            config = WorkerConfig(
                enable_execution_reconciliation=True,
                reconciliation_state_path=recon_state_path,
                gateway_state_path=str(state_path / "gateway_state.json"),
                positions_dir=str(state_path / "positions"),
                worker_state_path=str(state_path / "worker_state.json"),
                symbols=("BTCUSDT",),
                trend_symbols=("BTCUSDT",),
                range_symbols=(),
            )

            class MockTransport:
                def send_order(self, order: object) -> tuple[bool, str, str]:
                    return True, "exchange_order_123", ""

            # First worker instance
            worker1 = LiveTradingWorker(
                config=config,
                transport=MockTransport(),
            )

            # Register pending order
            assert worker1.execution_integration_layer is not None
            worker1.execution_integration_layer.reconciler.register_pending_order(
                client_order_id="client_123",
                symbol="BTCUSDT",
                side="buy",
                order_type="limit",
                quantity=1.0,
                price=50000.0,
            )

            # Simulate restart by creating new worker with same state path
            worker2 = LiveTradingWorker(
                config=config,
                transport=MockTransport(),
            )

            # Check if state was recovered
            assert worker2.execution_integration_layer is not None
            lifecycle = worker2.execution_integration_layer.get_order_lifecycle("client_123")
            assert lifecycle is not None
            assert lifecycle.symbol == "BTCUSDT"
            assert lifecycle.side == "buy"
            assert lifecycle.quantity == 1.0
