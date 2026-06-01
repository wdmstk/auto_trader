#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
SYMBOL="${SYMBOL:-BTCUSDT}"
TIMEFRAME="${TIMEFRAME:-1m}"
FROM_TS="${FROM_TS:-2026-01-01T00:00:00+00:00}"
TO_TS="${TO_TS:-2026-01-08T00:00:00+00:00}"
MIN_REGIME_HOLD_BARS="${MIN_REGIME_HOLD_BARS:-1}"
HIGH_VOL_COOLDOWN_BARS="${HIGH_VOL_COOLDOWN_BARS:-1}"

OHLCV_PATH="data/parquet/${SYMBOL}_${TIMEFRAME}.parquet"
FEATURE_PATH="data/features/${SYMBOL}_${TIMEFRAME}_features.parquet"
REGIME_PATH="data/regime/${SYMBOL}_${TIMEFRAME}_regime.parquet"

echo "== prepare long window visual data =="
echo "symbol=$SYMBOL timeframe=$TIMEFRAME from=$FROM_TS to=$TO_TS"

"$PYTHON_BIN" -m auto_trader.data \
  --symbol "$SYMBOL" \
  --timeframe "$TIMEFRAME" \
  --from-ts "$FROM_TS" \
  --to-ts "$TO_TS" \
  --output-dir data/parquet

"$PYTHON_BIN" -m auto_trader.features \
  --ohlcv-path "$OHLCV_PATH" \
  --symbol "$SYMBOL" \
  --timeframe "$TIMEFRAME" \
  --output-dir data/features

"$PYTHON_BIN" -m auto_trader.regime \
  --feature-path "$FEATURE_PATH" \
  --symbol "$SYMBOL" \
  --timeframe "$TIMEFRAME" \
  --output-dir data/regime \
  --min-regime-hold-bars "$MIN_REGIME_HOLD_BARS" \
  --high-vol-cooldown-bars "$HIGH_VOL_COOLDOWN_BARS"

"$PYTHON_BIN" -m auto_trader.strategy \
  --strategy range \
  --features-path "$FEATURE_PATH" \
  --regime-path "$REGIME_PATH" \
  --symbol "$SYMBOL" \
  --timeframe "$TIMEFRAME" \
  --output-dir data/signals

"$PYTHON_BIN" -m auto_trader.strategy \
  --strategy trend \
  --features-path "$FEATURE_PATH" \
  --regime-path "$REGIME_PATH" \
  --symbol "$SYMBOL" \
  --timeframe "$TIMEFRAME" \
  --output-dir data/signals

./scripts/walkforward_visual_check.sh

echo "Done. Open Streamlit and check Chart Overlay / Walkforward Visual Check."
