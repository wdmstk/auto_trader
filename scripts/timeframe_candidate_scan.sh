#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${OUT_DIR:-data/validation/timeframe_candidates}"
mkdir -p "$OUT_DIR"

SUMMARY_PATH="${SUMMARY_PATH:-$OUT_DIR/timeframe_comparison_summary.json}"
CANDIDATE_REPORT_PATH="${CANDIDATE_REPORT_PATH:-$OUT_DIR/candidate_report.json}"
DATA_ROOT="${DATA_ROOT:-data}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT,ADAUSDT,DOGEUSDT}"
FROM_TS="${FROM_TS:-2026-01-01T00:00:00+00:00}"
TO_TS="${TO_TS:-2026-04-01T00:00:00+00:00}"

echo "== timeframe candidate scan =="
echo "summary=$SUMMARY_PATH"
echo "candidate_report=$CANDIDATE_REPORT_PATH"
echo "symbols=$SYMBOLS from=$FROM_TS to=$TO_TS"

mkdir -p "$DATA_ROOT/parquet"
for symbol in ${SYMBOLS//,/ }; do
  base_1m="$DATA_ROOT/parquet/${symbol}_1m.parquet"
  if [[ ! -f "$base_1m" ]]; then
    echo "fetching missing 1m data: $symbol"
    SYMBOLS="$symbol" \
    TIMEFRAME=1m \
    FROM_TS="$FROM_TS" \
    TO_TS="$TO_TS" \
    STRICT=true \
    ./scripts/multi_symbol_data_pipeline.sh >/dev/null
  fi
done

SUMMARY_PATH="$SUMMARY_PATH" \
CANDIDATE_REPORT_PATH="$CANDIDATE_REPORT_PATH" \
TIMEFRAMES="${TIMEFRAMES:-15m,30m,1h}" \
SYMBOLS="$SYMBOLS" \
DATA_ROOT="$DATA_ROOT" \
ORDER_MODE="${ORDER_MODE:-market}" \
FEE_RATE="${FEE_RATE:-0.0002}" \
SLIPPAGE_RATE="${SLIPPAGE_RATE:-0.0002}" \
SPREAD_RATE="${SPREAD_RATE:-0.0001}" \
DELAY_BARS="${DELAY_BARS:-1}" \
ALLOWED_HOURS="${ALLOWED_HOURS:-}" \
RANGE_ENABLED_SYMBOLS="${RANGE_ENABLED_SYMBOLS:-}" \
TREND_ENABLED_SYMBOLS="${TREND_ENABLED_SYMBOLS:-}" \
./scripts/timeframe_comparison.sh
