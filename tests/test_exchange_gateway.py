from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_trader.exchange.errors import ErrorCode, RateLimitError
from auto_trader.exchange.gateway import GatewayConfig, OrderGateway, classify_error
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
    assert ev2.reason == "DUPLICATE_CLIENT_ORDER_ID"


def test_stale_signal_rejected() -> None:
    transport = FlakyTransport(0)
    gw = OrderGateway(transport, GatewayConfig(stale_signal_ttl_sec=1))
    req = _req(signal_ts=datetime.now(UTC) - timedelta(seconds=30))
    ev = gw.submit(req)
    assert ev.status == "rejected"
    assert ev.reason == "STALE_SIGNAL"


def test_retry_then_ack() -> None:
    transport = FlakyTransport(2)
    gw = OrderGateway(transport, GatewayConfig(max_retries=3))
    req = _req()
    ev = gw.submit(req)
    assert ev.status == "ack"
    assert transport.calls == 3


def test_limit_request_fields_are_preserved_in_event() -> None:
    transport = FlakyTransport(0)
    gw = OrderGateway(transport, GatewayConfig())
    req = _req()
    req = OrderRequest(**{**req.__dict__, "order_type": "limit", "limit_price": 64000.0})
    ev = gw.submit(req)
    assert ev.status == "ack"
    assert ev.order_type == "limit"
    assert ev.limit_price == 64000.0


def test_partial_fill_state_update() -> None:
    transport = FlakyTransport(0)
    gw = OrderGateway(transport, GatewayConfig())
    req = _req()
    ev = gw.submit(req)
    partial = gw.apply_fill_update(ev, 0.4)
    filled = gw.apply_fill_update(partial, 1.0)
    assert partial.status == "partial_filled"
    assert filled.status == "filled"


def test_runtime_gate_blocks_when_trading_disabled(tmp_path: Path) -> None:
    runtime_state = tmp_path / "control_state.json"
    runtime_state.write_text(
        json.dumps(
            {
                "trading_enabled": False,
                "emergency_stop": False,
                "close_all_requested": False,
                "updated_at": datetime.now(UTC).isoformat(),
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    transport = FlakyTransport(0)
    gw = OrderGateway(transport, GatewayConfig(runtime_state_path=str(runtime_state)))
    ev = gw.submit(_req())
    assert ev.status == "rejected"
    assert ev.reason == "RUNTIME_TRADING_DISABLED"
    assert transport.calls == 0


def test_runtime_gate_blocks_on_emergency_stop(tmp_path: Path) -> None:
    runtime_state = tmp_path / "control_state.json"
    runtime_state.write_text(
        json.dumps(
            {
                "trading_enabled": True,
                "emergency_stop": True,
                "close_all_requested": True,
                "updated_at": datetime.now(UTC).isoformat(),
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    transport = FlakyTransport(0)
    gw = OrderGateway(transport, GatewayConfig(runtime_state_path=str(runtime_state)))
    ev = gw.submit(_req())
    assert ev.status == "rejected"
    assert ev.reason == "RUNTIME_EMERGENCY_STOP"
    assert transport.calls == 0


def test_emergency_close_can_bypass_policy_gate(tmp_path: Path) -> None:
    runtime_state = tmp_path / "control_state.json"
    runtime_state.write_text(
        json.dumps(
            {
                "trading_enabled": False,
                "emergency_stop": True,
                "close_all_requested": True,
                "updated_at": datetime.now(UTC).isoformat(),
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    transport = FlakyTransport(0)
    gw = OrderGateway(transport, GatewayConfig(runtime_state_path=str(runtime_state)))
    req = OrderRequest(
        symbol="BTCUSDT",
        side="sell",
        qty=0.01,
        signal_ts=datetime.now(UTC),
        regime="HIGH_VOL",
        pass_filter=False,
        client_order_id="cid_emergency_bypass",
        order_type="market",
        limit_price=None,
    )
    ev = gw.submit(req, allow_runtime_gate=True, allow_policy_gate=True)
    assert ev.status == "ack"
    assert transport.calls == 1


def test_rate_limit_retries_with_retry_after() -> None:
    waits: list[float] = []

    class RateLimitTransport:
        def __init__(self) -> None:
            self.calls = 0

        def send_order(self, order: OrderRequest) -> tuple[bool, str, str]:
            self.calls += 1
            if self.calls == 1:
                return False, "", "rate_limit:retry_after=0.5"
            return True, f"ord_{order.client_order_id[-6:]}", "accepted"

    t = RateLimitTransport()
    gw = OrderGateway(
        t,
        GatewayConfig(max_retries=2, backoff_base_sec=0.1, max_backoff_sec=2.0),
        sleeper=waits.append,
    )
    ev = gw.submit(_req())
    assert ev.status == "ack"
    assert t.calls == 2
    assert waits == [0.5]


def test_classify_error_returns_code_and_exception() -> None:
    code, err = classify_error("rate_limit:retry_after=1.5")
    assert code == ErrorCode.RATE_LIMIT
    assert isinstance(err, RateLimitError)
    assert err.code == ErrorCode.RATE_LIMIT


def test_gateway_persists_state_and_recovers_from_backup(tmp_path: Path) -> None:
    state_path = tmp_path / "gateway_state.json"
    transport = FlakyTransport(0)
    gw = OrderGateway(
        transport,
        GatewayConfig(max_retries=1, state_path=str(state_path)),
    )
    req = _req(client_order_id="cid_state_test")
    ev = gw.submit(req)
    assert ev.status == "ack"
    assert state_path.exists()
    backup = state_path.with_suffix(".json.bak")
    assert backup.exists()

    state_path.write_text("{broken json", encoding="utf-8")
    gw2 = OrderGateway(transport, GatewayConfig(max_retries=1, state_path=str(state_path)))
    duplicate = gw2.submit(req)
    assert duplicate.status == "rejected"
    assert duplicate.reason == "DUPLICATE_CLIENT_ORDER_ID"


def test_non_retryable_error_returns_original_reason() -> None:
    class AuthErrorTransport:
        def __init__(self) -> None:
            self.calls = 0

        def send_order(self, order: OrderRequest) -> tuple[bool, str, str]:
            self.calls += 1
            return False, "", "http_error:400:code=-2015:msg=Invalid API-key"

    t = AuthErrorTransport()
    gw = OrderGateway(t, GatewayConfig(max_retries=3))
    ev = gw.submit(_req())
    assert ev.status == "rejected"
    assert ev.reason == "http_error:400:code=-2015:msg=Invalid API-key"
    assert t.calls == 1
