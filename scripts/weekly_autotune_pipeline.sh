#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

RUN_ROOT="${RUN_ROOT:-data/validation/weekly_autotune}"
RUN_EXPANSION="${RUN_EXPANSION:-1}"
RUN_REFINEMENT="${RUN_REFINEMENT:-1}"
RUN_WEEKLY="${RUN_WEEKLY:-1}"

EXPANSION_DIR="${EXPANSION_DIR:-$RUN_ROOT/autotune_expansion}"
REFINEMENT_DIR="${REFINEMENT_DIR:-$RUN_ROOT/core_refinement}"
MANIFEST_DIR="${MANIFEST_DIR:-$RUN_ROOT/manifest}"
WEEKLY_DIR="${WEEKLY_DIR:-$RUN_ROOT/weekly_revalidation}"

EXPANSION_SUMMARY_PATH="$EXPANSION_DIR/auto_tune_summary.json"
EXPANSION_FULL_MANIFEST_PATH="$EXPANSION_DIR/autotune_full_route_manifest.json"
REFINEMENT_SUMMARY_PATH="$REFINEMENT_DIR/auto_tune_summary.json"
REFINEMENT_FULL_MANIFEST_PATH="$REFINEMENT_DIR/autotune_full_route_manifest.json"

FINAL_MANIFEST_JSON="$MANIFEST_DIR/route_selection_manifest.json"
FINAL_MANIFEST_MD="$MANIFEST_DIR/route_selection_manifest.md"
FINAL_RUNTIME_ENV="$RUN_ROOT/route_selection_runtime.env"
FINAL_RUNTIME_TESTNET_ENV="$RUN_ROOT/route_selection_runtime.testnet.env"
FINAL_RUNTIME_PRODUCTION_ENV="$RUN_ROOT/route_selection_runtime.production.env"
FINAL_PRODUCTION_REPORT="$WEEKLY_DIR/weekly_revalidation_report.production.json"
RUNTIME_CANONICAL_PATH="$FINAL_MANIFEST_JSON"
RUNTIME_CANONICAL_SOURCE="manifest"
PIPELINE_SUMMARY_JSON="$RUN_ROOT/pipeline_summary.json"
PIPELINE_SUMMARY_MD="$RUN_ROOT/pipeline_summary.md"

REFINEMENT_TARGET_ROUTE_LIMIT="${REFINEMENT_TARGET_ROUTE_LIMIT:-${TARGET_ROUTE_LIMIT:-8}}"
STATISTICAL_GATE_MODE="${STATISTICAL_GATE_MODE:-soft}"
PIPELINE_RUN_ID="${PIPELINE_RUN_ID:-weekly-autotune-$(TZ=UTC date +%Y%m%dT%H%M%SZ)}"
export PIPELINE_RUN_ID

mkdir -p "$RUN_ROOT" "$EXPANSION_DIR" "$REFINEMENT_DIR" "$MANIFEST_DIR" "$WEEKLY_DIR"

echo "== weekly autotune pipeline =="
echo "run_root=$RUN_ROOT"
echo "run_expansion=$RUN_EXPANSION"
echo "run_refinement=$RUN_REFINEMENT"
echo "run_weekly=$RUN_WEEKLY"
echo "expansion_dir=$EXPANSION_DIR"
echo "refinement_dir=$REFINEMENT_DIR"
echo "manifest_dir=$MANIFEST_DIR"
echo "weekly_dir=$WEEKLY_DIR"
echo "statistical_gate_mode=$STATISTICAL_GATE_MODE"
echo "pipeline_run_id=$PIPELINE_RUN_ID"

current_manifest_path=""
current_manifest_md=""
selection_mode="none"

if [[ "$RUN_EXPANSION" == "1" ]]; then
  echo "== step: autotune expansion =="
  OUT_DIR="$EXPANSION_DIR" \
  TARGET_SELECTION_MODE=expansion \
  ./scripts/core_route_autotune.sh

  SUMMARY_PATH="$EXPANSION_SUMMARY_PATH" \
  OUT_DIR="$EXPANSION_DIR" \
  ./scripts/apply_autotune_core_candidates.sh

  current_manifest_path="$EXPANSION_FULL_MANIFEST_PATH"
  current_manifest_md="$EXPANSION_DIR/autotune_full_route_manifest.md"
  selection_mode="expansion"
fi

if [[ "$RUN_REFINEMENT" == "1" ]]; then
  echo "== step: autotune core refinement =="
  OUT_DIR="$REFINEMENT_DIR" \
  TARGET_SELECTION_MODE=core_refinement \
  TARGET_ROUTE_LIMIT="$REFINEMENT_TARGET_ROUTE_LIMIT" \
  ./scripts/core_route_autotune.sh

  SUMMARY_PATH="$REFINEMENT_SUMMARY_PATH" \
  OUT_DIR="$REFINEMENT_DIR" \
  BASE_MANIFEST_PATH="$current_manifest_path" \
  ./scripts/apply_autotune_core_candidates.sh

  current_manifest_path="$REFINEMENT_FULL_MANIFEST_PATH"
  current_manifest_md="$REFINEMENT_DIR/autotune_full_route_manifest.md"
  selection_mode="core_refinement"
fi

if [[ -z "$current_manifest_path" ]]; then
  if [[ -f "$FINAL_MANIFEST_JSON" ]]; then
    current_manifest_path="$FINAL_MANIFEST_JSON"
    if [[ -f "$FINAL_MANIFEST_MD" ]]; then
      current_manifest_md="$FINAL_MANIFEST_MD"
    fi
    selection_mode="existing_manifest"
    echo "== step: reuse existing manifest =="
    echo "manifest=$current_manifest_path"
  fi
fi

if [[ -z "$current_manifest_path" || ! -f "$current_manifest_path" ]]; then
  echo "final manifest was not produced" >&2
  exit 1
fi

if [[ "$current_manifest_path" != "$FINAL_MANIFEST_JSON" ]]; then
  cp "$current_manifest_path" "$FINAL_MANIFEST_JSON"
fi
if [[ -n "$current_manifest_md" && -f "$current_manifest_md" && "$current_manifest_md" != "$FINAL_MANIFEST_MD" ]]; then
  cp "$current_manifest_md" "$FINAL_MANIFEST_MD"
fi

write_runtime_env() {
  local route_path="$1"
  local env_path="$2"
  local execution_mode="$3"
  local statistical_gate_mode="$4"
  local pipeline_run_id="$5"
  PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
"$PYTHON_BIN" - "$route_path" "$env_path" "$execution_mode" "$statistical_gate_mode" "$pipeline_run_id" <<'EOF_PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
env_path = Path(sys.argv[2])
execution_mode = sys.argv[3]
statistical_gate_mode = sys.argv[4]
pipeline_run_id = sys.argv[5]
payload = json.loads(manifest_path.read_text(encoding="utf-8"))
selection = payload.get("selection", {})
trend_symbols = selection.get("trend_enabled_symbols", []) if isinstance(selection, dict) else []
range_symbols = selection.get("range_enabled_symbols", []) if isinstance(selection, dict) else []
symbols = []
for symbol in list(trend_symbols) + list(range_symbols):
    if isinstance(symbol, str) and symbol and symbol not in symbols:
        symbols.append(symbol)

lines = [
    f"ROUTE_SELECTION_PATH={manifest_path}",
    f"WEEKLY_REVALIDATION_REPORT_PATH={manifest_path}",
    f"WORKER_EXECUTION_MODE={execution_mode}",
    f"STATISTICAL_GATE_MODE={statistical_gate_mode}",
    f"PIPELINE_RUN_ID={pipeline_run_id}",
    f"SYMBOLS={','.join(symbols)}",
    f"TREND_ENABLED_SYMBOLS={','.join(str(symbol) for symbol in trend_symbols if isinstance(symbol, str))}",
    f"RANGE_ENABLED_SYMBOLS={','.join(str(symbol) for symbol in range_symbols if isinstance(symbol, str))}",
]
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(env_path)
EOF_PY
}

write_runtime_env "$RUNTIME_CANONICAL_PATH" "$FINAL_RUNTIME_ENV" "testnet" "$STATISTICAL_GATE_MODE" "$PIPELINE_RUN_ID"
write_runtime_env "$RUNTIME_CANONICAL_PATH" "$FINAL_RUNTIME_TESTNET_ENV" "testnet" "$STATISTICAL_GATE_MODE" "$PIPELINE_RUN_ID"

if [[ "$RUN_WEEKLY" == "1" ]]; then
  echo "== step: weekly revalidation =="
  OUT_DIR="$WEEKLY_DIR" \
  WEEKLY_CORE_FEEDBACK_ENV="$FINAL_RUNTIME_ENV" \
  ./scripts/weekly_strategy_revalidation_with_core.sh
  if [[ -f "$WEEKLY_DIR/weekly_revalidation_report.json" ]]; then
    RUNTIME_CANONICAL_PATH="$WEEKLY_DIR/weekly_revalidation_report.json"
    RUNTIME_CANONICAL_SOURCE="weekly_revalidation_report"
    write_runtime_env "$RUNTIME_CANONICAL_PATH" "$FINAL_RUNTIME_ENV" "testnet" "$STATISTICAL_GATE_MODE" "$PIPELINE_RUN_ID"
    write_runtime_env "$RUNTIME_CANONICAL_PATH" "$FINAL_RUNTIME_TESTNET_ENV" "testnet" "$STATISTICAL_GATE_MODE" "$PIPELINE_RUN_ID"
  fi
fi

if [[ -f "$WEEKLY_DIR/weekly_revalidation_report.json" && -f "$WEEKLY_DIR/manifest_vs_weekly_diff.json" ]]; then
  PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON_BIN" - \
    "$WEEKLY_DIR/weekly_revalidation_report.json" \
    "$WEEKLY_DIR/manifest_vs_weekly_diff.json" <<'EOF_PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

from auto_trader.analysis.revalidation import (
    apply_manifest_vs_weekly_diff_to_report,
)

report_path = Path(sys.argv[1])
diff_path = Path(sys.argv[2])

try:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    diff = json.loads(diff_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

report = apply_manifest_vs_weekly_diff_to_report(report, diff if isinstance(diff, dict) else None)
report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
print(report_path)
EOF_PY
fi

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
"$PYTHON_BIN" - \
  "$RUNTIME_CANONICAL_PATH" \
  "$FINAL_PRODUCTION_REPORT" \
  "$PIPELINE_RUN_ID" <<'EOF_PY'
from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from auto_trader.analysis.trade_routes import (
    build_trade_route_selection,
    validate_trade_route_selection,
)

source_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])
pipeline_run_id = sys.argv[3]

payload = json.loads(source_path.read_text(encoding="utf-8"))
selection = payload.get("selection", {})
if not isinstance(selection, dict):
    selection = {}

production_route_selection = build_trade_route_selection(
    payload,
    default_timeframe=str(selection.get("timeframe", "15m")).strip() or "15m",
    seed_manifest=payload,
    statistical_gate_mode="hard",
)
production_selection = deepcopy(selection)
production_selection.update(production_route_selection)
validate_trade_route_selection(production_selection)
payload["selection"] = production_selection
payload["run_id"] = str(payload.get("run_id", pipeline_run_id))
payload["generated_at"] = str(payload.get("generated_at", datetime.now(UTC).isoformat()))
payload["production_route_selection_source"] = str(source_path)
target_path.parent.mkdir(parents=True, exist_ok=True)
target_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
print(target_path)
EOF_PY

write_runtime_env "$FINAL_PRODUCTION_REPORT" "$FINAL_RUNTIME_PRODUCTION_ENV" "production" "hard" "$PIPELINE_RUN_ID"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
"$PYTHON_BIN" - \
  "$PIPELINE_SUMMARY_JSON" \
  "$PIPELINE_SUMMARY_MD" \
  "$RUN_ROOT" \
  "$EXPANSION_DIR" \
  "$REFINEMENT_DIR" \
  "$MANIFEST_DIR" \
  "$WEEKLY_DIR" \
  "$FINAL_MANIFEST_JSON" \
  "$FINAL_RUNTIME_ENV" \
  "$FINAL_RUNTIME_TESTNET_ENV" \
  "$FINAL_RUNTIME_PRODUCTION_ENV" \
  "$RUNTIME_CANONICAL_PATH" \
  "$RUNTIME_CANONICAL_SOURCE" \
  "$FINAL_PRODUCTION_REPORT" \
  "$selection_mode" \
  "$RUN_EXPANSION" \
  "$RUN_REFINEMENT" \
  "$RUN_WEEKLY" \
  "$STATISTICAL_GATE_MODE" \
  "$PIPELINE_RUN_ID" <<'EOF_PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

summary_json = Path(sys.argv[1])
summary_md = Path(sys.argv[2])
run_root = sys.argv[3]
expansion_dir = sys.argv[4]
refinement_dir = sys.argv[5]
manifest_dir = sys.argv[6]
weekly_dir = sys.argv[7]
final_manifest_json = sys.argv[8]
final_runtime_env = sys.argv[9]
final_runtime_testnet_env = sys.argv[10]
final_runtime_production_env = sys.argv[11]
runtime_canonical_path = sys.argv[12]
runtime_canonical_source = sys.argv[13]
production_runtime_path = sys.argv[14]
selection_mode = sys.argv[15]
run_expansion = sys.argv[16] == "1"
run_refinement = sys.argv[17] == "1"
run_weekly = sys.argv[18] == "1"
statistical_gate_mode = sys.argv[19]
pipeline_run_id = sys.argv[20]

payload = {
    "run_id": pipeline_run_id,
    "generated_at": datetime.now(UTC).isoformat(),
    "run_root": run_root,
    "steps": {
        "autotune_expansion": {"enabled": run_expansion, "out_dir": expansion_dir},
        "core_refinement": {"enabled": run_refinement, "out_dir": refinement_dir},
        "manifest": {
            "out_dir": manifest_dir,
            "route_selection_manifest": final_manifest_json,
            "runtime_env": final_runtime_env,
            "selection_mode": selection_mode,
        },
        "weekly_revalidation": {"enabled": run_weekly, "out_dir": weekly_dir},
    },
    "runtime": {
        "route_selection_path": runtime_canonical_path,
        "route_selection_source": runtime_canonical_source,
        "pre_weekly_manifest_path": final_manifest_json,
        "weekly_report_path": str(Path(weekly_dir) / "weekly_revalidation_report.json"),
        "strategy_quality_report_path": str(Path(weekly_dir) / "strategy_quality_report.md"),
        "strategy_quality_report_json_path": str(Path(weekly_dir) / "strategy_quality_report.json"),
        "ai_strategy_progress_report_path": str(Path(weekly_dir) / "ai_strategy_progress_report.md"),
        "ai_strategy_progress_report_json_path": str(Path(weekly_dir) / "ai_strategy_progress_report.json"),
        "production_route_selection_path": production_runtime_path,
    },
    "runtime_options": {
        "testnet": {
            "route_selection_path": runtime_canonical_path,
            "runtime_env": final_runtime_testnet_env,
            "execution_mode": "testnet",
            "statistical_gate_mode": "soft",
        },
        "production": {
            "route_selection_path": production_runtime_path,
            "runtime_env": final_runtime_production_env,
            "execution_mode": "production",
            "statistical_gate_mode": "hard",
        },
    },
    "policies": {
        "statistical_gate_mode": statistical_gate_mode,
    },
}
summary_json.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines = [
    "# Weekly Autotune Pipeline Summary",
    "",
    f"- generated_at: {payload['generated_at']}",
    f"- run_id: {pipeline_run_id}",
    f"- run_root: {run_root}",
    f"- selection_mode: {selection_mode}",
    f"- statistical_gate_mode: {statistical_gate_mode}",
    f"- runtime_route_selection_path: {runtime_canonical_path}",
    f"- runtime_route_selection_source: {runtime_canonical_source}",
    f"- production_route_selection_path: {production_runtime_path}",
    f"- testnet_runtime_env: {final_runtime_testnet_env}",
    f"- production_runtime_env: {final_runtime_production_env}",
    f"- pre_weekly_manifest_path: {final_manifest_json}",
    f"- weekly_report_path: {payload['runtime']['weekly_report_path']}",
    f"- strategy_quality_report_path: {payload['runtime']['strategy_quality_report_path']}",
    f"- strategy_quality_report_json_path: {payload['runtime']['strategy_quality_report_json_path']}",
    f"- ai_strategy_progress_report_path: {payload['runtime']['ai_strategy_progress_report_path']}",
    f"- ai_strategy_progress_report_json_path: {payload['runtime']['ai_strategy_progress_report_json_path']}",
    "",
    "## Steps",
    "",
    f"- autotune_expansion: {'on' if run_expansion else 'off'} ({expansion_dir})",
    f"- core_refinement: {'on' if run_refinement else 'off'} ({refinement_dir})",
    f"- manifest: {manifest_dir}",
    f"- weekly_revalidation: {'on' if run_weekly else 'off'} ({weekly_dir})",
]
summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(summary_json)
print(summary_md)
EOF_PY

if [[ -f "$WEEKLY_DIR/weekly_revalidation_report.json" ]]; then
  REPORT_PATH="$WEEKLY_DIR/weekly_revalidation_report.json" \
  OUT_PATH="$WEEKLY_DIR/portfolio_next_action_report.md" \
  ./scripts/portfolio_next_action_report.sh
  REPORT_PATH="$WEEKLY_DIR/weekly_revalidation_report.json" \
  OUT_PATH="$WEEKLY_DIR/strategy_quality_report.md" \
  ./scripts/strategy_quality_report.sh
  REPORT_PATH="$WEEKLY_DIR/weekly_revalidation_report.json" \
  OUT_PATH="$WEEKLY_DIR/strategy_quality_report.json" \
  ./scripts/strategy_quality_report.sh
  REPORT_PATH="$WEEKLY_DIR/weekly_revalidation_report.json" \
  OUT_PATH="$WEEKLY_DIR/ai_strategy_progress_report.md" \
  ./scripts/ai_strategy_progress_report.sh
  REPORT_PATH="$WEEKLY_DIR/weekly_revalidation_report.json" \
  OUT_PATH="$WEEKLY_DIR/ai_strategy_progress_report.json" \
  ./scripts/ai_strategy_progress_report.sh
fi

echo "done: $RUN_ROOT"
