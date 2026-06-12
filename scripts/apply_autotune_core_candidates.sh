#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
SUMMARY_PATH="${SUMMARY_PATH:-data/validation/core_route_autotune/auto_tune_summary.json}"
OUT_DIR="${OUT_DIR:-$(dirname "$SUMMARY_PATH")}"
OUT_JSON="${OUT_JSON:-$OUT_DIR/autotune_core_feedback.json}"
OUT_ENV="${OUT_ENV:-$OUT_DIR/autotune_core_feedback.env}"
OUT_MD="${OUT_MD:-$OUT_DIR/autotune_core_feedback.md}"
OUT_MANIFEST_JSON="${OUT_MANIFEST_JSON:-$OUT_DIR/autotune_route_manifest.json}"
OUT_MANIFEST_MD="${OUT_MANIFEST_MD:-$OUT_DIR/autotune_route_manifest.md}"
OUT_FULL_MANIFEST_JSON="${OUT_FULL_MANIFEST_JSON:-$OUT_DIR/autotune_full_route_manifest.json}"
OUT_FULL_MANIFEST_MD="${OUT_FULL_MANIFEST_MD:-$OUT_DIR/autotune_full_route_manifest.md}"
BASE_MANIFEST_PATH="${BASE_MANIFEST_PATH:-}"

mkdir -p "$OUT_DIR"

echo "== apply autotune core candidates =="
echo "summary=$SUMMARY_PATH"
echo "out_json=$OUT_JSON"
echo "out_env=$OUT_ENV"
echo "out_md=$OUT_MD"
echo "out_manifest_json=$OUT_MANIFEST_JSON"
echo "out_manifest_md=$OUT_MANIFEST_MD"
echo "out_full_manifest_json=$OUT_FULL_MANIFEST_JSON"
echo "out_full_manifest_md=$OUT_FULL_MANIFEST_MD"
if [[ -n "$BASE_MANIFEST_PATH" ]]; then
  echo "base_manifest_path=$BASE_MANIFEST_PATH"
fi

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
"$PYTHON_BIN" -m auto_trader.analysis.autotune_feedback \
  --summary-path "$SUMMARY_PATH" \
  --json-path "$OUT_JSON" \
  --env-path "$OUT_ENV" \
  --md-path "$OUT_MD" \
  --manifest-json-path "$OUT_MANIFEST_JSON" \
  --manifest-md-path "$OUT_MANIFEST_MD" \
  --full-manifest-json-path "$OUT_FULL_MANIFEST_JSON" \
  --full-manifest-md-path "$OUT_FULL_MANIFEST_MD" \
  --base-manifest-path "$BASE_MANIFEST_PATH"

echo "done: $OUT_JSON"
echo "done: $OUT_ENV"
echo "review: $OUT_MD"
echo "done: $OUT_MANIFEST_JSON"
echo "review: $OUT_MANIFEST_MD"
echo "done: $OUT_FULL_MANIFEST_JSON"
echo "review: $OUT_FULL_MANIFEST_MD"
