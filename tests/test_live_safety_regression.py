from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from auto_trader.exchange.gateway import GatewayConfig, OrderGateway
from auto_trader.exchange.idempotency import build_client_order_id
from auto_trader.exchange.models import OrderRequest
from auto_trader.runtime.control import FileStateControlHandler
from auto_trader.stateio import StateLockTimeoutError

pytestmark = pytest.mark.smoke


class DummyTransport:
    def __init__(self) -> None:
        self.calls = 0

    def send_order(self, order: OrderRequest) -> tuple[bool, str, str]:
        self.calls += 1
        return True, f"ord_{self.calls:06d}", "accepted"


def _req(*, client_order_id: str | None = None) -> OrderRequest:
    ts = datetime.now(UTC)
    return OrderRequest(
        symbol="BTCUSDT",
        side="buy",
        qty=0.01,
        signal_ts=ts,
        regime="RANGE",
        pass_filter=True,
        client_order_id=client_order_id
        or build_client_order_id(
            symbol="BTCUSDT",
            side="buy",
            signal_ts=ts,
            strategy="range",
        ),
    )


def test_live_safety_blocks_missing_runtime_state_in_live_mode(tmp_path: Path) -> None:
    transport = DummyTransport()
    gw = OrderGateway(
        transport,
        GatewayConfig(
            runtime_state_path=str(tmp_path / "missing_control_state.json"),
            require_runtime_state=True,
        ),
    )

    ev = gw.submit(_req())

    assert ev.status == "rejected"
    assert ev.reason == "RUNTIME_STATE_MISSING"
    assert transport.calls == 0


def test_live_safety_allows_explicit_dry_run_fail_open(tmp_path: Path) -> None:
    transport = DummyTransport()
    gw = OrderGateway(
        transport,
        GatewayConfig(
            runtime_state_path=str(tmp_path / "missing_control_state.json"),
            require_runtime_state=False,
            allow_runtime_state_fail_open=True,
        ),
    )

    ev = gw.submit(_req())

    assert ev.status == "ack"
    assert transport.calls == 1


def test_live_safety_rejects_duplicate_client_order_ids() -> None:
    transport = DummyTransport()
    gw = OrderGateway(transport, GatewayConfig())
    req = _req(client_order_id="cid_duplicate")

    first = gw.submit(req)
    second = gw.submit(req)

    assert first.status == "ack"
    assert second.status == "rejected"
    assert second.reason == "DUPLICATE_CLIENT_ORDER_ID"


def test_live_safety_traces_partial_fill_states() -> None:
    transport = DummyTransport()
    gw = OrderGateway(transport, GatewayConfig())
    req = _req(client_order_id="cid_partial_fill")

    ev = gw.submit(req)
    partial = gw.apply_fill_update(ev, 0.4)
    filled = gw.apply_fill_update(partial, 1.0)

    assert partial.status == "partial_filled"
    assert filled.status == "filled"


def test_runtime_control_recovers_from_backup_and_rejects_lock(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime" / "control_state.json"
    handler = FileStateControlHandler(state_path=state_path)
    handler.on_start()
    handler.on_emergency_stop()
    state_path.write_text("{broken json", encoding="utf-8")

    current = handler._read()
    assert current.emergency_stop is False
    assert current.trading_enabled is True

    lock_path = handler._lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("locked", encoding="utf-8")
    with pytest.raises(StateLockTimeoutError):
        handler.on_start()
