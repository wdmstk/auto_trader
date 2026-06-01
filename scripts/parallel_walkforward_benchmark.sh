#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT}"
STRATEGIES="${STRATEGIES:-range,trend}"
TIMEFRAME="${TIMEFRAME:-1m}"
FOLDS="${FOLDS:-4}"
OUTPUT_DIR="${OUTPUT_DIR:-data/analysis}"
BENCH_DIR="${BENCH_DIR:-data/validation}"
BENCH_PATH="${BENCH_PATH:-$BENCH_DIR/parallel_walkforward_benchmark.json}"

mkdir -p "$BENCH_DIR"

echo "== parallel walkforward benchmark =="
echo "symbols=$SYMBOLS strategies=$STRATEGIES timeframe=$TIMEFRAME folds=$FOLDS"

run_case() {
  local parallel="$1"
  local summary="$2"
  local started ended elapsed
  started="$(date +%s)"
  SYMBOLS="$SYMBOLS" \
  STRATEGIES="$STRATEGIES" \
  TIMEFRAME="$TIMEFRAME" \
  FOLDS="$FOLDS" \
  PARALLEL="$parallel" \
  OUTPUT_DIR="$OUTPUT_DIR" \
  SUMMARY_PATH="$summary" \
  ./scripts/parallel_walkforward.sh >/tmp/parallel_walkforward_${parallel}.log 2>&1 || true
  ended="$(date +%s)"
  elapsed=$((ended - started))
  echo "$elapsed"
}

seq_summary="$BENCH_DIR/parallel_walkforward_sequential_summary.jsonl"
par_summary="$BENCH_DIR/parallel_walkforward_parallel_summary.jsonl"

seq_sec="$(run_case 1 "$seq_summary")"
par_sec="$(run_case 4 "$par_summary")"

python - "$BENCH_PATH" "$seq_sec" "$par_sec" "$seq_summary" "$par_summary" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
seq_sec = int(sys.argv[2])
par_sec = int(sys.argv[3])
seq_summary = Path(sys.argv[4])
par_summary = Path(sys.argv[5])

speedup = (seq_sec / par_sec) if par_sec > 0 else 0.0
payload = {
    "sequential_sec": seq_sec,
    "parallel_sec": par_sec,
    "speedup": speedup,
    "sequential_summary": str(seq_summary),
    "parallel_summary": str(par_summary),
}
out.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=True))
PY

echo "benchmark=$BENCH_PATH"
