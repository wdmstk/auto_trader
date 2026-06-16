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
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

TIMEFRAME="${TIMEFRAME:-1m}"
STRATEGIES="${STRATEGIES:-range,trend}"
SYMBOLS_RAW="${SYMBOLS:-}"
OUT_DIR="${OUT_DIR:-data/validation/backtest_symbol_rotation}"
RUNS_DIR="${RUNS_DIR:-data/backtest/runs}"
SUMMARY_PATH="${SUMMARY_PATH:-$OUT_DIR/backtest_symbol_rotation_summary.jsonl}"
WEEKLY_REPORT_PATH="${WEEKLY_REPORT_PATH:-data/validation/weekly_revalidation/weekly_revalidation_report.json}"
RUN_STAMP="${RUN_STAMP:-$(date -u +"%Y%m%dT%H%M%SZ")}"

FEE_RATE="${FEE_RATE:-0.0004}"
SLIPPAGE_RATE="${SLIPPAGE_RATE:-0.0005}"
SPREAD_RATE="${SPREAD_RATE:-0.0003}"
DELAY_BARS="${DELAY_BARS:-1}"
ORDER_MODE="${ORDER_MODE:-market}"
MAKER_FEE_RATE="${MAKER_FEE_RATE:-0.0}"
TAKER_FEE_RATE="${TAKER_FEE_RATE:-0.0}"
LIMIT_OFFSET_RATE="${LIMIT_OFFSET_RATE:-0.0}"
LIMIT_PARTIAL_FILL_RATIO="${LIMIT_PARTIAL_FILL_RATIO:-0.1}"
LIMIT_BOOK_DEPTH_UNITS="${LIMIT_BOOK_DEPTH_UNITS:-0.0}"
LIMIT_QUEUE_AHEAD_UNITS="${LIMIT_QUEUE_AHEAD_UNITS:-0.0}"
LIMIT_VOLUME_PARTICIPATION_RATE="${LIMIT_VOLUME_PARTICIPATION_RATE:-0.0}"
ML_PATH="${ML_PATH:-}"

mkdir -p "$OUT_DIR" "$RUNS_DIR"
: > "$SUMMARY_PATH"

resolve_live_targets() {
  local report_path="$1"
  local targets_path="$2"
  local source_path="$3"
  "$PYTHON_BIN" - "$report_path" "$targets_path" "$source_path" "$TIMEFRAME" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

from auto_trader.analysis.trade_routes import resolve_live_trade_routes

report_path = Path(sys.argv[1])
targets_path = Path(sys.argv[2])
source_path = Path(sys.argv[3])
default_timeframe = sys.argv[4]

payload = resolve_live_trade_routes(report_path, default_timeframe=default_timeframe)
routes = payload.get("trade_routes", [])
if not isinstance(routes, list) or not routes:
    raise SystemExit(f"no live trade routes found in {report_path}")

source_path.write_text(str(payload.get("source", "")) + "\n", encoding="utf-8")
lines = ["symbol\tstrategy\ttimeframe\tcandidate_status\texpected_regime"]
for route in routes:
    if not isinstance(route, dict):
        continue
    symbol = str(route.get("symbol", "")).strip().upper()
    strategy = str(route.get("strategy", "")).strip()
    timeframe = str(route.get("timeframe", "")).strip() or default_timeframe
    candidate_status = str(route.get("candidate_status", "")).strip()
    expected_regime = str(route.get("expected_regime", "")).strip() or ("TREND" if strategy == "trend" else "RANGE")
    if not symbol or strategy not in {"trend", "range"}:
        continue
    lines.append("\t".join([symbol, strategy, timeframe, candidate_status, expected_regime]))
targets_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(targets_path)
PY
}

append_summary_row() {
  local payload_json="$1"
  "$PYTHON_BIN" - "$SUMMARY_PATH" "$payload_json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
payload = json.loads(sys.argv[2])
with summary_path.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(payload, ensure_ascii=True) + "\n")
PY
}

if [[ -n "$SYMBOLS_RAW" ]]; then
  MODE="explicit"
  IFS=',' read -r -a SYMBOLS_ARR <<< "$SYMBOLS_RAW"
  IFS=',' read -r -a STRATEGIES_ARR <<< "$STRATEGIES"
  if [[ "${#SYMBOLS_ARR[@]}" -eq 0 ]]; then
    echo "[NG] no symbols configured" >&2
    exit 1
  fi
  echo "== backtest symbol rotation =="
  echo "mode=$MODE"
  echo "symbols=${SYMBOLS_ARR[*]}"
  echo "strategies=${STRATEGIES_ARR[*]}"
  echo "timeframe=$TIMEFRAME"
  echo "run_stamp=$RUN_STAMP"
  echo "summary=$SUMMARY_PATH"
else
  MODE="auto"
  if [[ ! -f "$WEEKLY_REPORT_PATH" ]]; then
    echo "[NG] weekly report missing: $WEEKLY_REPORT_PATH" >&2
    echo "Run ./scripts/weekly_strategy_revalidation.sh first or set SYMBOLS=... to override." >&2
    exit 1
  fi
  TARGETS_PATH="$OUT_DIR/backtest_targets.tsv"
  TARGET_SOURCE_PATH="$OUT_DIR/backtest_targets.source"
  resolve_live_targets "$WEEKLY_REPORT_PATH" "$TARGETS_PATH" "$TARGET_SOURCE_PATH" >/dev/null
  TARGET_SOURCE="$(tr -d '\n' < "$TARGET_SOURCE_PATH")"
  echo "== backtest symbol rotation =="
  echo "mode=$MODE"
  echo "source=$TARGET_SOURCE"
  echo "report=$WEEKLY_REPORT_PATH"
  echo "timeframe=$TIMEFRAME"
  echo "run_stamp=$RUN_STAMP"
  echo "summary=$SUMMARY_PATH"
fi

run_one() {
  local symbol="$1"
  local strategy="$2"
  local route_timeframe="$3"
  local candidate_status="$4"
  local expected_regime="$5"
  local selection_source="$6"
  local ohlcv_path="data/parquet/${symbol}_${route_timeframe}.parquet"
  local signals_path="data/signals/${symbol}_${route_timeframe}_${strategy}_signals.parquet"
  local output_dir="$RUNS_DIR/$RUN_STAMP/${symbol}_${route_timeframe}_${strategy}"
  local log_path="$output_dir/run.log"

  mkdir -p "$output_dir"

  if [[ ! -f "$ohlcv_path" ]]; then
    append_summary_row "$(cat <<JSON
{"checked_at":"$(date -u +"%Y-%m-%dT%H:%M:%SZ")","symbol":"$symbol","timeframe":"$route_timeframe","strategy":"$strategy","candidate_status":"$candidate_status","expected_regime":"$expected_regime","selection_source":"$selection_source","status":"missing_ohlcv","ohlcv_path":"$ohlcv_path","signals_path":"$signals_path","output_dir":"$output_dir"}
JSON
)"
    echo "[NG] missing ohlcv: $ohlcv_path"
    return 0
  fi

  if [[ ! -f "$signals_path" ]]; then
    append_summary_row "$(cat <<JSON
{"checked_at":"$(date -u +"%Y-%m-%dT%H:%M:%SZ")","symbol":"$symbol","timeframe":"$route_timeframe","strategy":"$strategy","candidate_status":"$candidate_status","expected_regime":"$expected_regime","selection_source":"$selection_source","status":"missing_signals","ohlcv_path":"$ohlcv_path","signals_path":"$signals_path","output_dir":"$output_dir"}
JSON
)"
    echo "[NG] missing signals: $signals_path"
    return 0
  fi

  local cmd=(
    "$PYTHON_BIN" -m auto_trader.backtest
    --ohlcv-path "$ohlcv_path"
    --signals-path "$signals_path"
    --output-dir "$output_dir"
    --fee-rate "$FEE_RATE"
    --slippage-rate "$SLIPPAGE_RATE"
    --spread-rate "$SPREAD_RATE"
    --delay-bars "$DELAY_BARS"
    --order-mode "$ORDER_MODE"
    --maker-fee-rate "$MAKER_FEE_RATE"
    --taker-fee-rate "$TAKER_FEE_RATE"
    --limit-offset-rate "$LIMIT_OFFSET_RATE"
    --limit-partial-fill-ratio "$LIMIT_PARTIAL_FILL_RATIO"
    --limit-book-depth-units "$LIMIT_BOOK_DEPTH_UNITS"
    --limit-queue-ahead-units "$LIMIT_QUEUE_AHEAD_UNITS"
    --limit-volume-participation-rate "$LIMIT_VOLUME_PARTICIPATION_RATE"
  )

  local run_output=""
  if [[ -n "$ML_PATH" ]]; then
    cmd+=(--ml-path "$ML_PATH")
  fi

  if run_output="$("${cmd[@]}" 2>&1)"; then
    printf '%s\n' "$run_output" | tee "$log_path"
    append_summary_row "$(cat <<JSON
{"checked_at":"$(date -u +"%Y-%m-%dT%H:%M:%SZ")","symbol":"$symbol","timeframe":"$route_timeframe","strategy":"$strategy","candidate_status":"$candidate_status","expected_regime":"$expected_regime","selection_source":"$selection_source","status":"ok","ohlcv_path":"$ohlcv_path","signals_path":"$signals_path","output_dir":"$output_dir","portfolio_path":"$output_dir/portfolio.parquet","trades_path":"$output_dir/trades.parquet","metrics_path":"$output_dir/metrics.parquet","metadata_path":"$output_dir/metadata.json","stdout_tail":$(python - <<'PY' "$run_output"
from __future__ import annotations

import json
import sys

text = sys.argv[1]
lines = text.splitlines()[-20:]
print(json.dumps("\n".join(lines), ensure_ascii=True))
PY
)}
JSON
)"
    echo "[OK] $symbol/$strategy"
  else
    printf '%s\n' "$run_output" | tee "$log_path" >&2 || true
    append_summary_row "$(cat <<JSON
{"checked_at":"$(date -u +"%Y-%m-%dT%H:%M:%SZ")","symbol":"$symbol","timeframe":"$route_timeframe","strategy":"$strategy","candidate_status":"$candidate_status","expected_regime":"$expected_regime","selection_source":"$selection_source","status":"failed","ohlcv_path":"$ohlcv_path","signals_path":"$signals_path","output_dir":"$output_dir","log_path":"$log_path","stdout_tail":$(python - <<'PY' "$run_output"
from __future__ import annotations

import json
import sys

text = sys.argv[1]
lines = text.splitlines()[-20:]
print(json.dumps("\n".join(lines), ensure_ascii=True))
PY
)}
JSON
)"
    echo "[NG] $symbol/$strategy"
  fi
}

if [[ -n "$SYMBOLS_RAW" ]]; then
  for symbol in "${SYMBOLS_ARR[@]}"; do
    symbol="$(printf '%s' "$symbol" | tr '[:lower:]' '[:upper:]' | xargs)"
    [[ -n "$symbol" ]] || continue
    for strategy in "${STRATEGIES_ARR[@]}"; do
      strategy="$(printf '%s' "$strategy" | xargs)"
      [[ -n "$strategy" ]] || continue
      expected_regime="RANGE"
      if [[ "$strategy" == "trend" ]]; then
        expected_regime="TREND"
      fi
      run_one "$symbol" "$strategy" "$TIMEFRAME" "manual" "$expected_regime" "explicit_symbols"
    done
  done
else
  tail -n +2 "$TARGETS_PATH" | while IFS=$'\t' read -r symbol strategy route_timeframe candidate_status expected_regime; do
    symbol="$(printf '%s' "$symbol" | tr '[:lower:]' '[:upper:]' | xargs)"
    strategy="$(printf '%s' "$strategy" | xargs)"
    route_timeframe="$(printf '%s' "$route_timeframe" | xargs)"
    candidate_status="$(printf '%s' "$candidate_status" | xargs)"
    expected_regime="$(printf '%s' "$expected_regime" | xargs)"
    [[ -n "$symbol" && -n "$strategy" && -n "$route_timeframe" ]] || continue
    run_one "$symbol" "$strategy" "$route_timeframe" "$candidate_status" "$expected_regime" "$TARGET_SOURCE"
  done
fi

echo "done: summary=$SUMMARY_PATH"
