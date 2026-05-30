from __future__ import annotations

from datetime import UTC, datetime

import pytest

from auto_trader.position.manager import PositionConfig, PositionManager
from auto_trader.position.models import FillEvent


def _ts() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


def test_weighted_avg_entry_updates() -> None:
    pm = PositionManager(PositionConfig())
    pm.apply_fill(
        FillEvent(symbol="BTCUSDT", side="buy", qty=1.0, price=100.0, filled_at=_ts()),
    )
    s = pm.apply_fill(
        FillEvent(symbol="BTCUSDT", side="buy", qty=1.0, price=110.0, filled_at=_ts()),
    )
    assert s.qty == 2.0
    assert abs(s.avg_entry - 105.0) < 1e-9


def test_partial_close_keeps_avg_and_reduces_qty() -> None:
    pm = PositionManager(PositionConfig())
    pm.apply_fill(
        FillEvent(symbol="BTCUSDT", side="buy", qty=2.0, price=100.0, filled_at=_ts()),
    )
    s = pm.apply_fill(
        FillEvent(symbol="BTCUSDT", side="sell", qty=0.5, price=105.0, filled_at=_ts()),
    )
    assert abs(s.qty - 1.5) < 1e-9
    assert abs(s.avg_entry - 100.0) < 1e-9


def test_add_count_limit() -> None:
    pm = PositionManager(PositionConfig(max_add_count=2))
    pm.apply_fill(
        FillEvent(symbol="BTCUSDT", side="buy", qty=1.0, price=100.0, filled_at=_ts()),
    )
    pm.apply_fill(
        FillEvent(
            symbol="BTCUSDT",
            side="buy",
            qty=0.5,
            price=101.0,
            filled_at=_ts(),
            is_add=True,
        ),
    )
    s = pm.apply_fill(
        FillEvent(
            symbol="BTCUSDT",
            side="buy",
            qty=0.5,
            price=102.0,
            filled_at=_ts(),
            is_add=True,
        ),
    )
    assert s.add_count <= 2


def test_exposure_and_risk_block() -> None:
    pm = PositionManager(
        PositionConfig(max_symbol_exposure_pct=10.0, max_portfolio_exposure_pct=20.0),
    )
    pm.apply_fill(FillEvent(symbol="BTCUSDT", side="buy", qty=1.0, price=100.0, filled_at=_ts()))
    snap = pm.exposure_snapshot(mark_prices={"BTCUSDT": 100.0}, equity=500.0)
    assert snap["BTCUSDT_exposure_pct"] > 0
    assert pm.risk_blocked(mark_prices={"BTCUSDT": 100.0}, equity=500.0, symbol="BTCUSDT")


def test_invalid_fill_triggers_emergency_stop() -> None:
    pm = PositionManager(PositionConfig())
    with pytest.raises(ValueError):
        pm.apply_fill(
            FillEvent(
                symbol="BTCUSDT",
                side="buy",
                qty=0.0,
                price=100.0,
                filled_at=_ts(),
            )
        )
    assert pm.emergency_stopped() is True

    with pytest.raises(RuntimeError):
        pm.apply_fill(
            FillEvent(
                symbol="BTCUSDT",
                side="buy",
                qty=1.0,
                price=100.0,
                filled_at=_ts(),
            )
        )
