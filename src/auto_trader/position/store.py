from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.position.models import PositionState


class PositionStore:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def path(self) -> Path:
        return self.root_dir / "positions.parquet"

    def save(self, positions: list[PositionState]) -> Path:
        rows = [
            {
                "symbol": p.symbol,
                "side": p.side,
                "qty": p.qty,
                "avg_entry": p.avg_entry,
                "unrealized_pnl_pct": p.unrealized_pnl_pct,
                "add_count": p.add_count,
                "updated_at": p.updated_at,
            }
            for p in positions
        ]
        pd.DataFrame(rows).to_parquet(self.path(), index=False)
        return self.path()
