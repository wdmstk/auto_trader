from __future__ import annotations

from datetime import UTC, datetime, timedelta

from auto_trader.exchange.gateway import GatewayConfig, OrderGateway
from auto_trader.exchange.idempotency import build_client_order_id
from auto_trader.exchange.models import OrderRequest


class FlakyTransport:
    def __init__(self, fail_count: int) -> None:
        self.fail_count = fail_count
        self.calls = 0

    def send_order(self, order: OrderRequest) -> tuple[bool, str, str]:
        self.calls += 1
        if self.calls <= self.fail_count:
            return False, "", "timeout"
        return True, f"ord_{order.client_order_id[-6:]}", "accepted"


def _req(**kwargs: object) -> OrderRequest:
    ts = datetime.now(UTC)
    return OrderRequest(
        symbol=str(kwargs.get("symbol", "BTCUSDT")),
        side=str(kwargs.get("side", "buy")),  # type: ignore[arg-type]
        qty=_to_float(kwargs.get("qty", 1.0)),
        signal_ts=kwargs.get("signal_ts", ts),  # type: ignore[arg-type]
        regime=str(kwargs.get("regime", "RANGE")),
        pass_filter=bool(kwargs.get("pass_filter", True)),
        client_order_id=str(
            kwargs.get(
                "client_order_id",
                build_client_order_id(
                    symbol="BTCUSDT",
                    side="buy",
                    signal_ts=ts,
                    strategy="range",
                ),
            )
        ),
    )


def _to_float(v: object) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def test_duplicate_client_order_id_rejected() -> None:
    transport = FlakyTransport(0)
    gw = OrderGateway(transport, GatewayConfig())
    req = _req()
    ev1 = gw.submit(req)
    ev2 = gw.submit(req)
    assert ev1.status == "ack"
    assert ev2.status == "rejected"
    assert ev2.reason == "duplicate_client_order_id"


def test_stale_signal_rejected() -> None:
    transport = FlakyTransport(0)
    gw = OrderGateway(transport, GatewayConfig(stale_signal_ttl_sec=1))
    req = _req(signal_ts=datetime.now(UTC) - timedelta(seconds=30))
    ev = gw.submit(req)
    assert ev.status == "rejected"
    assert ev.reason == "stale_signal"


def test_retry_then_ack() -> None:
    transport = FlakyTransport(2)
    gw = OrderGateway(transport, GatewayConfig(max_retries=3))
    req = _req()
    ev = gw.submit(req)
    assert ev.status == "ack"
    assert transport.calls == 3


def test_partial_fill_state_update() -> None:
    transport = FlakyTransport(0)
    gw = OrderGateway(transport, GatewayConfig())
    req = _req()
    ev = gw.submit(req)
    partial = gw.apply_fill_update(ev, 0.4)
    filled = gw.apply_fill_update(partial, 1.0)
    assert partial.status == "partial_filled"
    assert filled.status == "filled"
