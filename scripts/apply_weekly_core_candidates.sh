#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
REPORT_PATH="${REPORT_PATH:-data/validation/symbol_candidate_exploration/timeframe_scan/candidate_report.json}"
WEEKLY_SCRIPT_PATH="${WEEKLY_SCRIPT_PATH:-scripts/weekly_strategy_revalidation.sh}"
OUT_DIR="${OUT_DIR:-data/validation/symbol_candidate_exploration}"
OUT_JSON="${OUT_JSON:-$OUT_DIR/weekly_core_feedback.json}"
OUT_ENV="${OUT_ENV:-$OUT_DIR/weekly_core_feedback.env}"
OUT_MD="${OUT_MD:-$OUT_DIR/weekly_core_feedback.md}"

mkdir -p "$OUT_DIR"

echo "== apply weekly core candidates =="
echo "report=$REPORT_PATH"
echo "weekly_script=$WEEKLY_SCRIPT_PATH"
echo "out_json=$OUT_JSON"
echo "out_env=$OUT_ENV"
echo "out_md=$OUT_MD"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
"$PYTHON_BIN" -m auto_trader.analysis.weekly_core_feedback \
  --report-path "$REPORT_PATH" \
  --weekly-script-path "$WEEKLY_SCRIPT_PATH" \
  --json-path "$OUT_JSON" \
  --env-path "$OUT_ENV" \
  --md-path "$OUT_MD"

echo "done: $OUT_JSON"
echo "done: $OUT_ENV"
echo "review: $OUT_MD"
