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
RUNTIME_CANONICAL_PATH="$FINAL_MANIFEST_JSON"
RUNTIME_CANONICAL_SOURCE="manifest"
PIPELINE_SUMMARY_JSON="$RUN_ROOT/pipeline_summary.json"
PIPELINE_SUMMARY_MD="$RUN_ROOT/pipeline_summary.md"

REFINEMENT_TARGET_ROUTE_LIMIT="${REFINEMENT_TARGET_ROUTE_LIMIT:-${TARGET_ROUTE_LIMIT:-8}}"
STATISTICAL_GATE_MODE="${STATISTICAL_GATE_MODE:-soft}"

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
  PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
"$PYTHON_BIN" - "$route_path" "$FINAL_RUNTIME_ENV" <<'EOF_PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
env_path = Path(sys.argv[2])
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
    f"SYMBOLS={','.join(symbols)}",
    f"TREND_ENABLED_SYMBOLS={','.join(str(symbol) for symbol in trend_symbols if isinstance(symbol, str))}",
    f"RANGE_ENABLED_SYMBOLS={','.join(str(symbol) for symbol in range_symbols if isinstance(symbol, str))}",
]
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(env_path)
EOF_PY
}

write_runtime_env "$RUNTIME_CANONICAL_PATH"

if [[ "$RUN_WEEKLY" == "1" ]]; then
  echo "== step: weekly revalidation =="
  OUT_DIR="$WEEKLY_DIR" \
  WEEKLY_CORE_FEEDBACK_ENV="$FINAL_RUNTIME_ENV" \
  ./scripts/weekly_strategy_revalidation_with_core.sh
  if [[ -f "$WEEKLY_DIR/weekly_revalidation_report.json" ]]; then
    RUNTIME_CANONICAL_PATH="$WEEKLY_DIR/weekly_revalidation_report.json"
    RUNTIME_CANONICAL_SOURCE="weekly_revalidation_report"
    write_runtime_env "$RUNTIME_CANONICAL_PATH"
  fi
fi

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
  "$RUNTIME_CANONICAL_PATH" \
  "$RUNTIME_CANONICAL_SOURCE" \
  "$selection_mode" \
  "$RUN_EXPANSION" \
  "$RUN_REFINEMENT" \
  "$RUN_WEEKLY" \
  "$STATISTICAL_GATE_MODE" <<'EOF_PY'
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
runtime_canonical_path = sys.argv[10]
runtime_canonical_source = sys.argv[11]
selection_mode = sys.argv[12]
run_expansion = sys.argv[13] == "1"
run_refinement = sys.argv[14] == "1"
run_weekly = sys.argv[15] == "1"
statistical_gate_mode = sys.argv[16]

payload = {
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
    f"- run_root: {run_root}",
    f"- selection_mode: {selection_mode}",
    f"- statistical_gate_mode: {statistical_gate_mode}",
    f"- runtime_route_selection_path: {runtime_canonical_path}",
    f"- runtime_route_selection_source: {runtime_canonical_source}",
    f"- pre_weekly_manifest_path: {final_manifest_json}",
    f"- weekly_report_path: {payload['runtime']['weekly_report_path']}",
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

echo "done: $RUN_ROOT"
