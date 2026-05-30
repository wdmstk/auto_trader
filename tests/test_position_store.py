from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from auto_trader.position.models import PositionState
from auto_trader.position.store import PositionStore


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
