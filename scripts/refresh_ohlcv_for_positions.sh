#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "python interpreter not found" >&2
    exit 127
  fi
fi

POSITIONS_DIR="${POSITIONS_DIR:-data/positions}"
OUTPUT_DIR="${OUTPUT_DIR:-data/live_pnl/ohlcv}"
# Download last 2 hours of data for LivePnL (refreshed every 5min)
HOURS_BACK="${HOURS_BACK:-2}"

echo "== refresh OHLCV for positions =="
echo "positions_dir=$POSITIONS_DIR output_dir=$OUTPUT_DIR hours_back=$HOURS_BACK"

mkdir -p "$OUTPUT_DIR"

"$PYTHON_BIN" - "$POSITIONS_DIR" "$OUTPUT_DIR" "$HOURS_BACK" <<'PY'
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_trader.position.store import PositionStore

positions_dir = Path(sys.argv[1])
output_dir = Path(sys.argv[2])
hours_back = int(sys.argv[3])

positions = PositionStore(positions_dir).load()

if not positions:
    print("positions=0 reason=no_active_positions")
    raise SystemExit(0)

# Collect unique symbol/timeframe combinations
symbol_timeframes = {}
for pos in positions:
    key = (pos.symbol, pos.timeframe)
    if key not in symbol_timeframes:
        symbol_timeframes[key] = pos.symbol

if not symbol_timeframes:
    print("positions=0 reason=no_valid_symbol_timeframes")
    raise SystemExit(0)

# Calculate time range
to_ts = datetime.now(UTC)
from_ts = to_ts - timedelta(hours=hours_back)

print(f"downloading for {len(symbol_timeframes)} symbol/timeframe pairs")
print(f"from_ts={from_ts.isoformat()} to_ts={to_ts.isoformat()}")

# Download OHLCV for each symbol/timeframe
success_count = 0
fail_count = 0

for (symbol, timeframe), _ in symbol_timeframes.items():
    print(f"downloading {symbol} {timeframe}...")
    try:
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "auto_trader.data",
                "--symbol", symbol,
                "--timeframe", timeframe,
                "--from-ts", from_ts.isoformat(),
                "--to-ts", to_ts.isoformat(),
                "--output-dir", str(output_dir),
            ],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            print(f"  [OK] {symbol} {timeframe}")
            success_count += 1
        else:
            print(f"  [NG] {symbol} {timeframe}: {result.stderr}")
            fail_count += 1
    except subprocess.TimeoutExpired:
        print(f"  [NG] {symbol} {timeframe}: timeout")
        fail_count += 1
    except Exception as e:
        print(f"  [NG] {symbol} {timeframe}: {e}")
        fail_count += 1

print(f"done: success={success_count} failed={fail_count} total={len(symbol_timeframes)}")
PY
