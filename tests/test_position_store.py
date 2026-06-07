from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from auto_trader.position.models import PositionState
from auto_trader.position.store import PositionStore
from auto_trader.stateio import StateLockTimeoutError


def test_position_store_saves_parquet(tmp_path: Path) -> None:
    store = PositionStore(tmp_path)
    p = PositionState(
        symbol="ETHUSDT",
        side="buy",
        qty=1.2,
        avg_entry=123.4,
        unrealized_pnl_pct=0.05,
        add_count=1,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    out = store.save([p])
    assert out.exists()
    df = pd.read_parquet(out)
    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "ETHUSDT"
    assert df.iloc[0]["route_key"] == "legacy:ETHUSDT:15m"


def test_position_store_recovers_from_backup_when_primary_is_corrupted(tmp_path: Path) -> None:
    store = PositionStore(tmp_path)
    p1 = PositionState(
        symbol="BTCUSDT",
        side="buy",
        qty=0.5,
        avg_entry=100.0,
        unrealized_pnl_pct=0.01,
        add_count=0,
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    p2 = PositionState(
        symbol="ETHUSDT",
        side="sell",
        qty=1.5,
        avg_entry=200.0,
        unrealized_pnl_pct=-0.03,
        add_count=1,
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    store.save([p1])
    store.save([p2])  # backup contains p1
    store.path().write_text("not-parquet", encoding="utf-8")

    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0].symbol == "BTCUSDT"


def test_position_store_loads_legacy_schema_without_route_columns(tmp_path: Path) -> None:
    legacy = pd.DataFrame(
        [
            {
                "symbol": "BTCUSDT",
                "side": "buy",
                "qty": 1.0,
                "avg_entry": 100.0,
                "unrealized_pnl_pct": 0.0,
                "add_count": 0,
                "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
            }
        ]
    )
    store = PositionStore(tmp_path)
    legacy.to_parquet(store.path(), index=False)

    loaded = store.load()

    assert loaded[0].route_key == "legacy:BTCUSDT:15m"


def test_position_store_fails_when_lock_is_held(tmp_path: Path) -> None:
    store = PositionStore(tmp_path, lock_timeout_sec=0.01)
    store.lock_path().write_text("locked", encoding="utf-8")
    with pytest.raises(StateLockTimeoutError):
        store.save([])
