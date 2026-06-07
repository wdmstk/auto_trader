#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
DATA_ROOT="${DATA_ROOT:-data}"
OUT_DIR="${OUT_DIR:-data/validation/symbol_candidate_exploration}"
SCAN_OUT_DIR="${SCAN_OUT_DIR:-$OUT_DIR/timeframe_scan}"
BASE_URL="${BASE_URL:-https://api.binance.com}"
MAX_CANDIDATES="${MAX_CANDIDATES:-20}"
MIN_QUOTE_VOLUME="${MIN_QUOTE_VOLUME:-30000000.0}"
EXCLUDED_SYMBOLS="${EXCLUDED_SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT,ADAUSDT}"

mkdir -p "$OUT_DIR" "$SCAN_OUT_DIR"

MANIFEST_JSON="$OUT_DIR/symbol_exploration_manifest.json"
MANIFEST_ENV="$OUT_DIR/symbol_exploration.env"

echo "== symbol candidate exploration =="
echo "out_dir=$OUT_DIR"
echo "scan_out_dir=$SCAN_OUT_DIR"
echo "limit=$MAX_CANDIDATES min_quote_volume=$MIN_QUOTE_VOLUME"
echo "excluded_symbols=$EXCLUDED_SYMBOLS"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
"$PYTHON_BIN" -m auto_trader.analysis.symbol_exploration \
  --base-url "$BASE_URL" \
  --data-root "$DATA_ROOT" \
  --limit "$MAX_CANDIDATES" \
  --min-quote-volume "$MIN_QUOTE_VOLUME" \
  --exclude-symbols "$EXCLUDED_SYMBOLS" \
  --json-path "$MANIFEST_JSON" \
  --env-path "$MANIFEST_ENV"

set -a
source "$MANIFEST_ENV"
set +a

if [[ -z "${SYMBOLS:-}" ]]; then
  echo "no eligible new symbols found"
  exit 0
fi

SUMMARY_PATH="$SCAN_OUT_DIR/timeframe_comparison_summary.json" \
CANDIDATE_REPORT_PATH="$SCAN_OUT_DIR/candidate_report.json" \
OUT_DIR="$SCAN_OUT_DIR" \
SYMBOLS="$SYMBOLS" \
TIMEFRAMES="${TIMEFRAMES:-15m,30m,1h}" \
./scripts/timeframe_candidate_scan.sh

echo "done: $OUT_DIR"
