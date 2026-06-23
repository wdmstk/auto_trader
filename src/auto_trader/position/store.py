from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, cast

import pandas as pd

from auto_trader.position.models import PositionState
from auto_trader.stateio import FileLock, atomic_write_file

logger = logging.getLogger(__name__)


class PositionStore:
    def __init__(self, root_dir: str | Path, *, lock_timeout_sec: float = 1.0) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.lock_timeout_sec = lock_timeout_sec

    def path(self) -> Path:
        return self.root_dir / "positions.parquet"

    def lock_path(self) -> Path:
        return self.root_dir / "positions.parquet.lock"

    def save(self, positions: list[PositionState]) -> Path:
        rows = [
            {
                "symbol": p.symbol,
                "strategy": p.strategy,
                "timeframe": p.timeframe,
                "route_key": p.route_key,
                "side": p.side,
                "qty": p.qty,
                "avg_entry": p.avg_entry,
                "unrealized_pnl_pct": p.unrealized_pnl_pct,
                "add_count": p.add_count,
                "updated_at": p.updated_at,
            }
            for p in positions
        ]
        with FileLock(self.lock_path(), timeout_sec=self.lock_timeout_sec):
            return atomic_write_file(self.path(), writer=lambda p: _write_parquet(rows, p))

    def load(self) -> list[PositionState]:
        with FileLock(self.lock_path(), timeout_sec=self.lock_timeout_sec):
            df = _read_parquet_with_recovery(self.path())
        out: list[PositionState] = []
        for row in df.itertuples(index=False):
            updated_at = row.updated_at
            if hasattr(updated_at, "to_pydatetime"):
                updated_at = updated_at.to_pydatetime()
            out.append(
                PositionState(
                    symbol=str(row.symbol),
                    strategy=str(getattr(row, "strategy", "legacy")),
                    timeframe=str(getattr(row, "timeframe", "15m")),
                    route_key=str(getattr(row, "route_key", "")),
                    side=str(row.side),  # type: ignore[arg-type]
                    qty=float(cast(Any, row.qty)),
                    avg_entry=float(cast(Any, row.avg_entry)),
                    unrealized_pnl_pct=float(cast(Any, row.unrealized_pnl_pct)),
                    add_count=int(cast(Any, row.add_count)),
                    updated_at=cast(Any, updated_at),
                )
            )
        return out


def _write_parquet(rows: list[dict[str, object]], path: Path) -> None:
    pd.DataFrame(rows).to_parquet(path, index=False)
    with path.open("rb") as f:
        os.fsync(f.fileno())


def _read_parquet_with_recovery(path: Path) -> pd.DataFrame:
    backup = path.with_suffix(f"{path.suffix}.bak")
    try:
        return pd.read_parquet(path)
    except Exception:
        logger.warning("positions parquet unreadable at %s, trying backup", path, exc_info=True)
        if backup.exists():
            logger.info("recovered positions from backup %s", backup)
            return pd.read_parquet(backup)
    return pd.DataFrame(
        columns=[
            "symbol",
            "strategy",
            "timeframe",
            "route_key",
            "side",
            "qty",
            "avg_entry",
            "unrealized_pnl_pct",
            "add_count",
            "updated_at",
        ]
    )
