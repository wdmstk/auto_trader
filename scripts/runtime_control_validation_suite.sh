#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "python interpreter not found" >&2
    exit 127
  fi
fi
OUT_DIR="${OUT_DIR:-data/validation/runtime_control_suite}"
mkdir -p "$OUT_DIR"

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

STATUS_FILE="$OUT_DIR/runtime_control_validation_suite.steps.tsv"
: > "$STATUS_FILE"

log_step() {
  local name="$1"
  local status="$2"
  local log_path="$3"
  printf '%s\t%s\t%s\n' "$name" "$status" "$log_path" >> "$STATUS_FILE"
}

run_step() {
  local name="$1"
  shift
  local log_path="$OUT_DIR/${name}.log"
  printf '== %s ==\n' "$name"
  if "$@" >"$log_path" 2>&1; then
    log_step "$name" "ok" "$log_path"
    printf '[OK] %s\n' "$name"
  else
    log_step "$name" "failed" "$log_path"
    printf '[NG] %s (see %s)\n' "$name" "$log_path" >&2
    tail -n 40 "$log_path" >&2 || true
    exit 1
  fi
}

run_step prepare_long_window_visual_data \
  env \
    OUTPUT_DIR="$OUT_DIR/analysis" \
    ./scripts/prepare_long_window_visual_data.sh

run_step weekly_strategy_revalidation \
  env \
    OUT_DIR="$OUT_DIR/weekly_revalidation" \
    ./scripts/weekly_strategy_revalidation.sh

run_step parallel_walkforward \
  env \
    SUMMARY_PATH="$OUT_DIR/parallel_walkforward_summary.jsonl" \
    OUTPUT_DIR="$OUT_DIR/analysis" \
    ./scripts/parallel_walkforward.sh

run_step chaos_test \
  env \
    OUT_DIR="$OUT_DIR/chaos" \
    ./scripts/chaos_test.sh

"$PYTHON_BIN" - "$STATUS_FILE" "$OUT_DIR/runtime_control_validation_suite.json" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

status_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])

steps: list[dict[str, str]] = []
for line in status_path.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    name, status, log_path = line.split("\t", 2)
    steps.append({"name": name, "status": status, "log_path": log_path})

artifacts = {
    "analysis_dir": str(summary_path.parent / "analysis"),
    "weekly_revalidation_dir": str(summary_path.parent / "weekly_revalidation"),
    "parallel_walkforward_summary": str(summary_path.parent / "parallel_walkforward_summary.jsonl"),
    "chaos_dir": str(summary_path.parent / "chaos"),
}

payload = {
    "checked_at": datetime.now(UTC).isoformat(),
    "status": "pass" if all(step["status"] == "ok" for step in steps) else "fail",
    "steps": steps,
    "artifacts": artifacts,
}
summary_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
print(summary_path)
PY

printf 'done: %s\n' "$OUT_DIR"
