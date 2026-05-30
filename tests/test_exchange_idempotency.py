from __future__ import annotations

from datetime import UTC, datetime

from auto_trader.exchange.idempotency import build_client_order_id


def test_client_order_id_is_stable_for_same_input() -> None:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    cid1 = build_client_order_id(symbol="BTCUSDT", side="buy", signal_ts=ts, strategy="range")
    cid2 = build_client_order_id(symbol="BTCUSDT", side="buy", signal_ts=ts, strategy="range")
    assert cid1 == cid2


def test_client_order_id_changes_with_nonce() -> None:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    cid1 = build_client_order_id(
        symbol="BTCUSDT",
        side="buy",
        signal_ts=ts,
        strategy="range",
        nonce="a",
    )
    cid2 = build_client_order_id(
        symbol="BTCUSDT",
        side="buy",
        signal_ts=ts,
        strategy="range",
        nonce="b",
    )
    assert cid1 != cid2
