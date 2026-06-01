#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT}"
TIMEFRAME="${TIMEFRAME:-1m}"
FROM_TS="${FROM_TS:-2026-01-01T00:00:00+00:00}"
TO_TS="${TO_TS:-2026-01-08T00:00:00+00:00}"
MIN_REGIME_HOLD_BARS="${MIN_REGIME_HOLD_BARS:-1}"
HIGH_VOL_COOLDOWN_BARS="${HIGH_VOL_COOLDOWN_BARS:-1}"
OUTPUT_DIR="${OUTPUT_DIR:-data/validation}"
SUMMARY_PATH="${SUMMARY_PATH:-$OUTPUT_DIR/multi_symbol_pipeline_summary.jsonl}"
STRICT="${STRICT:-false}"
RANGE_RSI_MIN="${RANGE_RSI_MIN:-40}"
RANGE_RSI_MAX="${RANGE_RSI_MAX:-50}"
RANGE_WICK_RATIO_MIN="${RANGE_WICK_RATIO_MIN:-0.3}"
RANGE_MEAN_REVERSION_DISTANCE_MAX="${RANGE_MEAN_REVERSION_DISTANCE_MAX:--0.1}"
RANGE_EXIT_MEAN_REVERSION_NEUTRAL_ABS="${RANGE_EXIT_MEAN_REVERSION_NEUTRAL_ABS:-0.05}"
RANGE_DEFAULT_POSITION_SIZE_RATIO="${RANGE_DEFAULT_POSITION_SIZE_RATIO:-0.1}"
RANGE_REQUIRE_REVERSAL_CANDLE="${RANGE_REQUIRE_REVERSAL_CANDLE:-false}"
RANGE_MIN_ENTRY_SCORE="${RANGE_MIN_ENTRY_SCORE:-1.0}"
RANGE_REENTRY_COOLDOWN_BARS="${RANGE_REENTRY_COOLDOWN_BARS:-0}"
RANGE_ENABLED_SYMBOLS="${RANGE_ENABLED_SYMBOLS:-}"
TREND_MIN_ENTRY_SCORE="${TREND_MIN_ENTRY_SCORE:-1.0}"
TREND_REENTRY_COOLDOWN_BARS="${TREND_REENTRY_COOLDOWN_BARS:-0}"
TREND_ENABLED_SYMBOLS="${TREND_ENABLED_SYMBOLS:-}"

mkdir -p "$OUTPUT_DIR" data/parquet data/features data/regime data/signals

echo "== multi symbol data pipeline =="
echo "symbols=$SYMBOLS timeframe=$TIMEFRAME from=$FROM_TS to=$TO_TS"
echo "summary=$SUMMARY_PATH"
echo "range_cfg: rsi=[$RANGE_RSI_MIN,$RANGE_RSI_MAX] wick>=$RANGE_WICK_RATIO_MIN mr<=$RANGE_MEAN_REVERSION_DISTANCE_MAX require_reversal=$RANGE_REQUIRE_REVERSAL_CANDLE"
echo "range_gate: min_score=$RANGE_MIN_ENTRY_SCORE cooldown=$RANGE_REENTRY_COOLDOWN_BARS enabled=[$RANGE_ENABLED_SYMBOLS]"
echo "trend_gate: min_score=$TREND_MIN_ENTRY_SCORE cooldown=$TREND_REENTRY_COOLDOWN_BARS enabled=[$TREND_ENABLED_SYMBOLS]"

success_count=0
fail_count=0

run_symbol() {
  local symbol="$1"
  local ohlcv_path="data/parquet/${symbol}_${TIMEFRAME}.parquet"
  local feature_path="data/features/${symbol}_${TIMEFRAME}_features.parquet"
  local regime_path="data/regime/${symbol}_${TIMEFRAME}_regime.parquet"

  "$PYTHON_BIN" -m auto_trader.data \
    --symbol "$symbol" \
    --timeframe "$TIMEFRAME" \
    --from-ts "$FROM_TS" \
    --to-ts "$TO_TS" \
    --output-dir data/parquet

  "$PYTHON_BIN" -m auto_trader.features \
    --ohlcv-path "$ohlcv_path" \
    --symbol "$symbol" \
    --timeframe "$TIMEFRAME" \
    --output-dir data/features

  "$PYTHON_BIN" -m auto_trader.regime \
    --feature-path "$feature_path" \
    --symbol "$symbol" \
    --timeframe "$TIMEFRAME" \
    --output-dir data/regime \
    --min-regime-hold-bars "$MIN_REGIME_HOLD_BARS" \
    --high-vol-cooldown-bars "$HIGH_VOL_COOLDOWN_BARS"

  "$PYTHON_BIN" -m auto_trader.strategy \
    --strategy range \
    --features-path "$feature_path" \
    --regime-path "$regime_path" \
    --symbol "$symbol" \
    --timeframe "$TIMEFRAME" \
    --output-dir data/signals \
    --range-rsi-min "$RANGE_RSI_MIN" \
    --range-rsi-max "$RANGE_RSI_MAX" \
    --range-wick-ratio-min "$RANGE_WICK_RATIO_MIN" \
    --range-mean-reversion-distance-max "$RANGE_MEAN_REVERSION_DISTANCE_MAX" \
    --range-exit-mean-reversion-neutral-abs "$RANGE_EXIT_MEAN_REVERSION_NEUTRAL_ABS" \
    --range-default-position-size-ratio "$RANGE_DEFAULT_POSITION_SIZE_RATIO" \
    --range-require-reversal-candle "$RANGE_REQUIRE_REVERSAL_CANDLE" \
    --range-min-entry-score "$RANGE_MIN_ENTRY_SCORE" \
    --range-reentry-cooldown-bars "$RANGE_REENTRY_COOLDOWN_BARS" \
    --range-enabled-symbols "$RANGE_ENABLED_SYMBOLS"

  "$PYTHON_BIN" -m auto_trader.strategy \
    --strategy trend \
    --features-path "$feature_path" \
    --regime-path "$regime_path" \
    --symbol "$symbol" \
    --timeframe "$TIMEFRAME" \
    --output-dir data/signals \
    --trend-min-entry-score "$TREND_MIN_ENTRY_SCORE" \
    --trend-reentry-cooldown-bars "$TREND_REENTRY_COOLDOWN_BARS" \
    --trend-enabled-symbols "$TREND_ENABLED_SYMBOLS"
}

for symbol in ${SYMBOLS//,/ }; do
  started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "--- symbol=$symbol started_at=$started_at ---"
  if run_symbol "$symbol"; then
    ended_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    success_count=$((success_count + 1))
    echo "{\"symbol\":\"$symbol\",\"status\":\"ok\",\"started_at\":\"$started_at\",\"ended_at\":\"$ended_at\"}" >> "$SUMMARY_PATH"
    echo "[OK] $symbol"
  else
    ended_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    fail_count=$((fail_count + 1))
    echo "{\"symbol\":\"$symbol\",\"status\":\"failed\",\"started_at\":\"$started_at\",\"ended_at\":\"$ended_at\"}" >> "$SUMMARY_PATH"
    echo "[NG] $symbol (continued)"
  fi
done

echo "done: success=$success_count failed=$fail_count"
if [[ "$STRICT" == "true" && "$fail_count" -gt 0 ]]; then
  exit 1
fi
