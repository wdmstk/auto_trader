#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${OUT_DIR:-data/validation/weekly_revalidation}"
CORE_FEEDBACK_ENV="${WEEKLY_CORE_FEEDBACK_ENV:-data/validation/symbol_candidate_exploration/weekly_core_feedback.env}"
BASELINE_OVERRIDE_ENV="${WEEKLY_BASELINE_OVERRIDE_ENV:-}"

echo "== weekly strategy revalidation with core feedback =="
echo "core_feedback_env=$CORE_FEEDBACK_ENV"
if [[ -n "$BASELINE_OVERRIDE_ENV" ]]; then
  echo "baseline_override_env=$BASELINE_OVERRIDE_ENV"
fi

if [[ -f "$CORE_FEEDBACK_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$CORE_FEEDBACK_ENV"
  set +a
  echo "loaded core feedback env"
else
  echo "core feedback env not found, running baseline defaults"
fi

if [[ -n "$BASELINE_OVERRIDE_ENV" && -f "$BASELINE_OVERRIDE_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$BASELINE_OVERRIDE_ENV"
  set +a
  echo "loaded baseline override env"
fi

main_status=0
set +e
./scripts/weekly_strategy_revalidation.sh
main_status=$?
set -e

OUT_DIR="$OUT_DIR" \
REPORT_PATH="$OUT_DIR/candidate_report.json" \
OUT_PATH="$OUT_DIR/result_list.md" \
./scripts/weekly_revalidation_results_list.sh || true

OUT_DIR="$OUT_DIR" \
REPORT_PATH="$OUT_DIR/weekly_revalidation_report.json" \
OUT_PATH="$OUT_DIR/range_probe_result_list.md" \
./scripts/weekly_revalidation_probe_results_list.sh || true

exit "$main_status"
