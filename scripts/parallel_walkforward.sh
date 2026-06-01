#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT}"
STRATEGIES="${STRATEGIES:-range,trend}"
TIMEFRAME="${TIMEFRAME:-1m}"
FOLDS="${FOLDS:-4}"
PARALLEL="${PARALLEL:-4}"
OUTPUT_DIR="${OUTPUT_DIR:-data/analysis}"
SUMMARY_PATH="${SUMMARY_PATH:-data/validation/parallel_walkforward_summary.jsonl}"

mkdir -p "$(dirname "$SUMMARY_PATH")"
: > "$SUMMARY_PATH"

echo "== parallel walkforward =="
echo "symbols=$SYMBOLS strategies=$STRATEGIES timeframe=$TIMEFRAME folds=$FOLDS parallel=$PARALLEL"
echo "summary=$SUMMARY_PATH"

run_one() {
  local symbol="$1"
  local strategy="$2"
  local started_at ended_at
  local ohlcv_path="data/parquet/${symbol}_${TIMEFRAME}.parquet"
  local signals_path="data/signals/${symbol}_${TIMEFRAME}_${strategy}_signals.parquet"
  started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

  if [[ ! -f "$ohlcv_path" ]]; then
    echo "{\"symbol\":\"$symbol\",\"strategy\":\"$strategy\",\"status\":\"missing_ohlcv\",\"path\":\"$ohlcv_path\",\"started_at\":\"$started_at\"}" >> "$SUMMARY_PATH"
    return 0
  fi
  if [[ ! -f "$signals_path" ]]; then
    echo "{\"symbol\":\"$symbol\",\"strategy\":\"$strategy\",\"status\":\"missing_signals\",\"path\":\"$signals_path\",\"started_at\":\"$started_at\"}" >> "$SUMMARY_PATH"
    return 0
  fi

  if out="$("$PYTHON_BIN" -m auto_trader.analysis \
    --ohlcv-path "$ohlcv_path" \
    --signals-path "$signals_path" \
    --symbol "$symbol" \
    --timeframe "$TIMEFRAME" \
    --strategy "$strategy" \
    --folds "$FOLDS" \
    --output-dir "$OUTPUT_DIR" 2>&1)"; then
    ended_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    echo "{\"symbol\":\"$symbol\",\"strategy\":\"$strategy\",\"status\":\"ok\",\"started_at\":\"$started_at\",\"ended_at\":\"$ended_at\",\"result\":$out}" >> "$SUMMARY_PATH"
    echo "[OK] $symbol/$strategy"
  else
    ended_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    esc_out="$(printf '%s' "$out" | tr '\n' ' ' | sed 's/"/\\"/g')"
    echo "{\"symbol\":\"$symbol\",\"strategy\":\"$strategy\",\"status\":\"failed\",\"started_at\":\"$started_at\",\"ended_at\":\"$ended_at\",\"error\":\"$esc_out\"}" >> "$SUMMARY_PATH"
    echo "[NG] $symbol/$strategy"
  fi
}

jobs_running=0
for symbol in ${SYMBOLS//,/ }; do
  for strategy in ${STRATEGIES//,/ }; do
    run_one "$symbol" "$strategy" &
    jobs_running=$((jobs_running + 1))
    if (( jobs_running >= PARALLEL )); then
      wait -n || true
      jobs_running=$((jobs_running - 1))
    fi
  done
done

wait || true
echo "done. summary=$SUMMARY_PATH"
