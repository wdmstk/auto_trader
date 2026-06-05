#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
ORDER_EVENTS_PATH="${ORDER_EVENTS_PATH:-data/exchange/order_events.jsonl}"
POSITIONS_DIR="${POSITIONS_DIR:-data/positions}"

echo "== refresh positions from order events =="
echo "order_events=$ORDER_EVENTS_PATH positions_dir=$POSITIONS_DIR"

"$PYTHON_BIN" - "$ORDER_EVENTS_PATH" "$POSITIONS_DIR" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from auto_trader.position.manager import PositionManager
from auto_trader.position.models import FillEvent
from auto_trader.position.store import PositionStore

order_events_path = Path(sys.argv[1])
positions_dir = Path(sys.argv[2])

if not order_events_path.exists():
    print("rows=0 reason=order_events_missing")
    raise SystemExit(0)

rows: list[dict[str, object]] = []
for line in order_events_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        payload = json.loads(line)
    except Exception:
        continue
    if not isinstance(payload, dict):
        continue
    if str(payload.get("status", "")).lower() != "ack":
        continue
    action = str(payload.get("action", "")).lower()
    if action not in {"entry", "add", "exit", "emergency_close"}:
        continue
    symbol = str(payload.get("symbol", "")).strip()
    side = str(payload.get("side", "")).strip().lower()
    qty = float(payload.get("qty", 0.0) or 0.0)
    price = float(payload.get("price", 0.0) or 0.0)
    if not symbol or side not in {"buy", "sell"} or qty <= 0.0 or price <= 0.0:
        continue
    filled_at = payload.get("ack_at") or payload.get("sent_at") or payload.get("requested_at")
    try:
        filled_ts = pd.to_datetime(filled_at, utc=True).to_pydatetime() if filled_at else datetime.now(UTC)
    except Exception:
        filled_ts = datetime.now(UTC)
    rows.append(
        {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "filled_at": filled_ts,
            "is_add": action == "add",
        }
    )

if not rows:
    print("rows=0 reason=no_ack_fills")
    raise SystemExit(0)

pm = PositionManager()
for row in rows:
    pm.apply_fill(
        FillEvent(
            symbol=str(row["symbol"]),
            side=str(row["side"]),  # type: ignore[arg-type]
            qty=float(row["qty"]),
            price=float(row["price"]),
            filled_at=row["filled_at"],  # type: ignore[arg-type]
            is_add=bool(row["is_add"]),
        )
    )

store = PositionStore(positions_dir)
store.save(pm.all_positions())
print(f"rows={len(rows)} positions={len(pm.all_positions())}")
PY
