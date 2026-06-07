from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from auto_trader.position.manager import PositionConfig, PositionManager
from auto_trader.position.models import FillEvent
from auto_trader.position.store import PositionStore


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Apply a fill and persist position state.")
    p.add_argument("--symbol", required=True)
    p.add_argument("--side", choices=["buy", "sell"], required=True)
    p.add_argument("--qty", type=float, required=True)
    p.add_argument("--price", type=float, required=True)
    p.add_argument("--is-add", action="store_true")
    p.add_argument("--strategy", default="legacy")
    p.add_argument("--timeframe", default="15m")
    p.add_argument("--output-dir", default="data/positions")
    return p


def main() -> int:
    args = build_parser().parse_args()
    pm = PositionManager(PositionConfig())
    fill = FillEvent(
        symbol=args.symbol,
        side=args.side,
        qty=args.qty,
        price=args.price,
        filled_at=datetime.now(UTC),
        is_add=bool(args.is_add),
        strategy=args.strategy,
        timeframe=args.timeframe,
    )
    state = pm.apply_fill(fill)
    store = PositionStore(Path(args.output_dir))
    store.save(pm.all_positions())
    print(
        f"symbol={state.symbol} qty={state.qty:.6f} avg_entry={state.avg_entry:.4f} "
        f"add_count={state.add_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
