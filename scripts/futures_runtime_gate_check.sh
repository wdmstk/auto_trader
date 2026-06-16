#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

SYMBOL="${SYMBOL:-BTCUSDT}"
QTY="${QTY:-0.001}"
RUNTIME_STATE_PATH="${RUNTIME_STATE_PATH:-data/runtime/control_state.json}"
GATEWAY_STATE_PATH="${GATEWAY_STATE_PATH:-data/exchange/gateway_state.json}"
EVENT_LOG="${EVENT_LOG:-data/gui/control_events.jsonl}"
OUTPUT_DIR="${OUTPUT_DIR:-data/validation}"
RESULT_PATH="${RESULT_PATH:-$OUTPUT_DIR/futures_runtime_gate_check.jsonl}"
RUN_ID="${RUN_ID:-${PIPELINE_RUN_ID:-}}"

mkdir -p "$OUTPUT_DIR"

append_event() {
  local action="$1"
  local now
  now="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  printf '%s\n' "{\"action\":\"$action\",\"requested_at\":\"$now\",\"applied_at\":\"$now\",\"result\":\"accepted\"}" >> "$EVENT_LOG"
}

run_runtime_once() {
  python -m auto_trader.runtime
}

run_order_once() {
  python -m auto_trader.exchange \
    --mode testnet-futures-live \
    --symbol "$SYMBOL" \
    --side buy \
    --qty "$QTY" \
    --pass-filter \
    --runtime-state-path "$RUNTIME_STATE_PATH" \
    --state-path "$GATEWAY_STATE_PATH"
}

record_result() {
  local scenario="$1"
  local runtime_out="$2"
  local order_out="$3"
  local ts
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  python - "$RESULT_PATH" "$ts" "$scenario" "$runtime_out" "$order_out" "$RUN_ID" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
checked_at = sys.argv[2]
scenario = sys.argv[3]
runtime_out = sys.argv[4]
order_out = sys.argv[5]
run_id = sys.argv[6]
row = {
    "checked_at": checked_at,
    "run_id": run_id,
    "scenario": scenario,
    "runtime": runtime_out,
    "order": order_out,
}
with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(row, ensure_ascii=True) + "\n")
PY
}

echo "Running futures runtime gate check..."
echo "result_path=$RESULT_PATH"
echo "run_id=$RUN_ID"

# 1) STOP -> RUNTIME_TRADING_DISABLED
append_event "STOP"
runtime_out="$(run_runtime_once)"
order_out="$(run_order_once || true)"
record_result "STOP" "$runtime_out" "$order_out"
echo "[STOP] $runtime_out"
echo "[STOP] $order_out"

# 2) EMERGENCY_STOP -> RUNTIME_EMERGENCY_STOP
append_event "EMERGENCY_STOP"
runtime_out="$(run_runtime_once)"
order_out="$(run_order_once || true)"
record_result "EMERGENCY_STOP" "$runtime_out" "$order_out"
echo "[EMERGENCY_STOP] $runtime_out"
echo "[EMERGENCY_STOP] $order_out"

# 3) START -> ack expected
append_event "START"
runtime_out="$(run_runtime_once)"
order_out="$(run_order_once || true)"
record_result "START" "$runtime_out" "$order_out"
echo "[START] $runtime_out"
echo "[START] $order_out"

echo "Done. Evidence: $RESULT_PATH"
