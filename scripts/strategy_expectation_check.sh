#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

FEATURES_PATH="${FEATURES_PATH:-data/features/BTCUSDT_1m_features.parquet}"
REGIME_PATH="${REGIME_PATH:-data/regime/BTCUSDT_1m_regime.parquet}"
RISK_INPUT_PATH="${RISK_INPUT_PATH:-data/risk/risk_input.parquet}"
RISK_EVAL_PATH="${RISK_EVAL_PATH:-data/risk/risk_eval.parquet}"
RUNTIME_STATE_PATH="${RUNTIME_STATE_PATH:-data/runtime/control_state.json}"
SIGNALS_DIR="${SIGNALS_DIR:-data/signals}"
OUTPUT_DIR="${OUTPUT_DIR:-data/validation/strategy_check}"
SYMBOL="${SYMBOL:-BTCUSDT}"
TIMEFRAME="${TIMEFRAME:-1m}"
ML_ARTIFACT_PATH="${ML_ARTIFACT_PATH:-}"

mkdir -p "$OUTPUT_DIR"

run_e2e_for() {
  local strategy="$1"
  local signals_path="$2"
  local out_dir="$OUTPUT_DIR/e2e_${strategy}"
  mkdir -p "$out_dir"
  "$PYTHON_BIN" -m auto_trader.e2e \
    --signals-path "$signals_path" \
    --risk-eval-path "$RISK_EVAL_PATH" \
    --runtime-state-path "$RUNTIME_STATE_PATH" \
    --output-dir "$out_dir"
}

echo "== strategy expectation check =="

echo "[1/4] build range signals"
range_build_out="$("$PYTHON_BIN" -m auto_trader.strategy \
  --strategy range \
  --features-path "$FEATURES_PATH" \
  --regime-path "$REGIME_PATH" \
  --risk-path "$RISK_INPUT_PATH" \
  --symbol "$SYMBOL" \
  --timeframe "$TIMEFRAME" \
  --output-dir "$SIGNALS_DIR" \
  ${ML_ARTIFACT_PATH:+--ml-artifact-path "$ML_ARTIFACT_PATH"})"
echo "$range_build_out"
RANGE_SIGNALS_PATH="$(echo "$range_build_out" | sed -n 's/^saved=\([^ ]*\).*/\1/p')"
if [[ -z "$RANGE_SIGNALS_PATH" ]]; then
  RANGE_SIGNALS_PATH="$SIGNALS_DIR/${SYMBOL}_${TIMEFRAME}_range_signals.parquet"
fi

echo "[2/4] build trend signals"
trend_build_out="$("$PYTHON_BIN" -m auto_trader.strategy \
  --strategy trend \
  --features-path "$FEATURES_PATH" \
  --regime-path "$REGIME_PATH" \
  --risk-path "$RISK_INPUT_PATH" \
  --symbol "$SYMBOL" \
  --timeframe "$TIMEFRAME" \
  --output-dir "$SIGNALS_DIR" \
  ${ML_ARTIFACT_PATH:+--ml-artifact-path "$ML_ARTIFACT_PATH"})"
echo "$trend_build_out"
TREND_SIGNALS_PATH="$(echo "$trend_build_out" | sed -n 's/^saved=\([^ ]*\).*/\1/p')"
if [[ -z "$TREND_SIGNALS_PATH" ]]; then
  TREND_SIGNALS_PATH="$SIGNALS_DIR/${SYMBOL}_${TIMEFRAME}_trend_signals.parquet"
fi

echo "[3/4] e2e check for range"
range_e2e="$(run_e2e_for range "$RANGE_SIGNALS_PATH" || true)"
echo "$range_e2e"

echo "[4/4] e2e check for trend"
trend_e2e="$(run_e2e_for trend "$TREND_SIGNALS_PATH" || true)"
echo "$trend_e2e"

"$PYTHON_BIN" - "$RANGE_SIGNALS_PATH" "$TREND_SIGNALS_PATH" "$range_e2e" "$trend_e2e" "$OUTPUT_DIR/summary.json" <<'PY'
import json
import sys
from pathlib import Path
import pandas as pd

range_path = Path(sys.argv[1])
trend_path = Path(sys.argv[2])
range_e2e_raw = sys.argv[3]
trend_e2e_raw = sys.argv[4]
out_path = Path(sys.argv[5])

range_df = pd.read_parquet(range_path)
trend_df = pd.read_parquet(trend_path)

required_cols = {"symbol", "timestamp", "entry_signal", "pass_filter", "regime"}
range_cols_ok = required_cols.issubset(range_df.columns)
trend_cols_ok = required_cols.issubset(trend_df.columns)

def parse_json_or_text(raw: str):
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}

range_e2e = parse_json_or_text(range_e2e_raw)
trend_e2e = parse_json_or_text(trend_e2e_raw)

summary = {
    "range": {
        "signals_path": str(range_path),
        "rows": int(len(range_df)),
        "schema_ok": bool(range_cols_ok),
        "e2e": range_e2e,
    },
    "trend": {
        "signals_path": str(trend_path),
        "rows": int(len(trend_df)),
        "schema_ok": bool(trend_cols_ok),
        "e2e": trend_e2e,
    },
}
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(summary, ensure_ascii=True), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=True))
PY

echo "summary: $OUTPUT_DIR/summary.json"
