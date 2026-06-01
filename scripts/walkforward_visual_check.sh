#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
OHLCV_PATH="${OHLCV_PATH:-data/parquet/BTCUSDT_1m.parquet}"
RANGE_SIGNALS_PATH="${RANGE_SIGNALS_PATH:-data/signals/BTCUSDT_1m_range_signals.parquet}"
TREND_SIGNALS_PATH="${TREND_SIGNALS_PATH:-data/signals/BTCUSDT_1m_trend_signals.parquet}"
SYMBOL="${SYMBOL:-BTCUSDT}"
TIMEFRAME="${TIMEFRAME:-1m}"
FOLDS="${FOLDS:-4}"
OUTPUT_DIR="${OUTPUT_DIR:-data/analysis}"

echo "== walkforward visual check =="
"$PYTHON_BIN" -m auto_trader.analysis \
  --ohlcv-path "$OHLCV_PATH" \
  --signals-path "$RANGE_SIGNALS_PATH" \
  --symbol "$SYMBOL" \
  --timeframe "$TIMEFRAME" \
  --strategy range \
  --folds "$FOLDS" \
  --output-dir "$OUTPUT_DIR"

"$PYTHON_BIN" -m auto_trader.analysis \
  --ohlcv-path "$OHLCV_PATH" \
  --signals-path "$TREND_SIGNALS_PATH" \
  --symbol "$SYMBOL" \
  --timeframe "$TIMEFRAME" \
  --strategy trend \
  --folds "$FOLDS" \
  --output-dir "$OUTPUT_DIR"

echo "generated in: $OUTPUT_DIR"
