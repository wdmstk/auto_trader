#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${OUT_DIR:-data/validation/weekly_revalidation}"
CORE_FEEDBACK_ENV="${WEEKLY_CORE_FEEDBACK_ENV:-data/validation/symbol_candidate_exploration/weekly_core_feedback.env}"
BASELINE_OVERRIDE_ENV="${WEEKLY_BASELINE_OVERRIDE_ENV:-}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

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

MANIFEST_PATH="${ROUTE_SELECTION_PATH:-}"

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

if [[ -n "$MANIFEST_PATH" && -f "$MANIFEST_PATH" && -f "$OUT_DIR/weekly_revalidation_report.json" ]]; then
  MANIFEST_PATH="$MANIFEST_PATH" \
  WEEKLY_SUMMARY_PATH="$OUT_DIR/manifest_route_summary.json" \
  WEEKLY_CANDIDATE_PATH="$OUT_DIR/manifest_candidate_report.json" \
  WEEKLY_REPORT_PATH="$OUT_DIR/weekly_revalidation_report.json" \
  STATISTICAL_REPORT_PATH="${STATISTICAL_DIR:-data/validation/statistical_qualification}/qualification_report.json" \
  OUTPUT_JSON="$OUT_DIR/manifest_vs_weekly_diff.json" \
  OUTPUT_MD="$OUT_DIR/manifest_vs_weekly_diff.md" \
  ./scripts/manifest_weekly_diff_report.sh || true

  if [[ -f "$OUT_DIR/manifest_vs_weekly_diff.json" ]]; then
    "$PYTHON_BIN" - "$OUT_DIR/weekly_revalidation_report.json" "$OUT_DIR/manifest_vs_weekly_diff.json" <<'PY'
import json
import os
import sys
from pathlib import Path


def _load_dict(path_str: str) -> dict:
    path = Path(path_str)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


report_path = Path(sys.argv[1])
diff_path = Path(sys.argv[2])
report = _load_dict(str(report_path))
diff_payload = _load_dict(str(diff_path))
rows = diff_payload.get("rows", [])
if not isinstance(rows, list):
    rows = []

summary_rows = []
metric_match_count = 0
oos_window_drift_count = 0
for row in rows:
    if not isinstance(row, dict):
        continue
    delta = row.get("delta", {})
    source = row.get("source", {})
    weekly = row.get("weekly", {})
    source_fold = source.get("fold_snapshot", {}) if isinstance(source, dict) else {}
    weekly_fold = weekly.get("fold_snapshot", {}) if isinstance(weekly, dict) else {}
    weekly_stat = weekly.get("statistical_oos", {}) if isinstance(weekly, dict) else {}
    source_final = source_fold.get("final_oos", {}) if isinstance(source_fold, dict) else {}
    weekly_final = weekly_fold.get("final_oos", {}) if isinstance(weekly_fold, dict) else {}
    metric_match = all(abs(_safe_float(v)) < 1e-12 for v in (delta or {}).values())
    source_trade_oos_days = _safe_float(source_final.get("days"))
    weekly_trade_oos_days = _safe_float(weekly_final.get("days"))
    weekly_fold_oos_days = _safe_float(weekly_stat.get("days"))
    fold_window_drift_days = weekly_fold_oos_days - source_trade_oos_days
    if metric_match:
        metric_match_count += 1
    if abs(fold_window_drift_days) > 1e-12:
        oos_window_drift_count += 1
    summary_rows.append(
        {
            "route_key": str(row.get("route_key", "")),
            "selected_stage": str(row.get("selected_stage", "")),
            "metric_match": metric_match,
            "manifest_candidate_status": str((row.get("manifest", {}) or {}).get("candidate_status", "")),
            "weekly_candidate_status": str((weekly or {}).get("candidate_status", "")),
            "weekly_statistical_status": str((weekly or {}).get("statistical_status", "")),
            "source_trade_oos_days": source_trade_oos_days,
            "weekly_trade_oos_days": weekly_trade_oos_days,
            "weekly_fold_oos_days": weekly_fold_oos_days,
            "fold_window_drift_days": fold_window_drift_days,
            "closed_trades_mean": _safe_float((weekly or {}).get("closed_trades_mean")),
            "statistical_reasons": list((weekly or {}).get("statistical_reasons", []))
            if isinstance((weekly or {}).get("statistical_reasons", []), list)
            else [],
        }
    )

summary = {
    "status": "match" if metric_match_count == len(summary_rows) else "mismatch",
    "route_count": len(summary_rows),
    "metric_match_count": metric_match_count,
    "metric_mismatch_count": len(summary_rows) - metric_match_count,
    "oos_window_drift_count": oos_window_drift_count,
    "summary_md_path": str(diff_path.with_suffix(".md")),
    "summary_json_path": str(diff_path),
    "rows": summary_rows,
}

report["manifest_weekly_diff"] = summary
overview = report.get("overview", {})
if isinstance(overview, dict):
    overview["manifest_weekly_diff"] = {
        "status": summary["status"],
        "route_count": summary["route_count"],
        "metric_match_count": summary["metric_match_count"],
        "metric_mismatch_count": summary["metric_mismatch_count"],
        "oos_window_drift_count": summary["oos_window_drift_count"],
    }
    report["overview"] = overview


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.tmp.{os.getpid()}"
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


_atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
PY
  fi
fi

exit "$main_status"
