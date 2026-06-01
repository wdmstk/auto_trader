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
  printf '%s\n' "{\"checked_at\":\"$ts\",\"scenario\":\"$scenario\",\"runtime\":\"$runtime_out\",\"order\":\"$order_out\"}" >> "$RESULT_PATH"
}

echo "Running futures runtime gate check..."
echo "result_path=$RESULT_PATH"

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
