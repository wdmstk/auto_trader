#!/usr/bin/env bash
set -euo pipefail

# Longrun checkpoint collector (default: 8h window, 30min interval)
# Records checkpoint status into JSONL and optional markdown summary.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

DURATION_SEC="${DURATION_SEC:-28800}"      # 8h
INTERVAL_SEC="${INTERVAL_SEC:-1800}"       # 30min
OUTPUT_DIR="${OUTPUT_DIR:-data/validation}"
JSONL_PATH="${JSONL_PATH:-$OUTPUT_DIR/longrun_checkpoints.jsonl}"
MD_PATH="${MD_PATH:-$OUTPUT_DIR/longrun_checkpoints.md}"
RUNTIME_METRICS_JSONL="${RUNTIME_METRICS_JSONL:-$OUTPUT_DIR/runtime_metrics.jsonl}"
RUNTIME_METRICS_HEALTH_REPORT="${RUNTIME_METRICS_HEALTH_REPORT:-$OUTPUT_DIR/runtime_metrics_health_report.json}"
ENABLE_RUNTIME_METRICS="${ENABLE_RUNTIME_METRICS:-true}"
ENABLE_APPEND_RECORD="${ENABLE_APPEND_RECORD:-true}"
RECORD_PATH="${RECORD_PATH:-}"

RUNTIME_STATE="${RUNTIME_STATE:-data/runtime/control_state.json}"
RUNTIME_LOCK="${RUNTIME_LOCK:-data/runtime/control_state.json.lock}"
RUNTIME_BAK="${RUNTIME_BAK:-data/runtime/control_state.json.bak}"

NOTIFY_STATE="${NOTIFY_STATE:-data/ops/notify_state.json}"
NOTIFY_LOCK="${NOTIFY_LOCK:-data/ops/notify_state.json.lock}"
NOTIFY_BAK="${NOTIFY_BAK:-data/ops/notify_state.json.bak}"

RUNTIME_PROC_PATTERN="${RUNTIME_PROC_PATTERN:-auto_trader.runtime --watch}"
NOTIFY_PROC_PATTERN="${NOTIFY_PROC_PATTERN:-auto_trader.notify --watch}"
OPS_PROC_PATTERN="${OPS_PROC_PATTERN:-auto_trader.ops --watch}"

START_WATCHERS="${START_WATCHERS:-false}"
WATCHER_PIDS=()

mkdir -p "$OUTPUT_DIR"

cleanup() {
  if [[ "${#WATCHER_PIDS[@]}" -gt 0 ]]; then
    echo "Stopping watcher processes..."
    for pid in "${WATCHER_PIDS[@]}"; do
      kill "$pid" >/dev/null 2>&1 || true
    done
  fi
}
trap cleanup EXIT INT TERM

read_updated_at() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo ""
    return 0
  fi
  python - "$path" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
try:
    raw = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    print("")
    raise SystemExit(0)
if isinstance(raw, dict):
    print(str(raw.get("updated_at", "")))
else:
    print("")
PY
}

mtime_or_zero() {
  local path="$1"
  if [[ -f "$path" ]]; then
    stat -c %Y "$path"
  else
    echo "0"
  fi
}

proc_alive() {
  local pattern="$1"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    echo "true"
  else
    echo "false"
  fi
}

json_escape() {
  python - "$1" <<'PY'
import json
import sys
print(json.dumps(sys.argv[1], ensure_ascii=True))
PY
}

start_epoch="$(date +%s)"
end_epoch="$((start_epoch + DURATION_SEC))"
checkpoint=0

prev_runtime_updated_at="$(read_updated_at "$RUNTIME_STATE")"
prev_notify_updated_at="$(read_updated_at "$NOTIFY_STATE")"
prev_runtime_bak_mtime="$(mtime_or_zero "$RUNTIME_BAK")"
prev_notify_bak_mtime="$(mtime_or_zero "$NOTIFY_BAK")"

{
  echo "# 8h Continuous Run Checkpoints"
  echo
  echo "- started_at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "- duration_sec: $DURATION_SEC"
  echo "- interval_sec: $INTERVAL_SEC"
  echo "- jsonl: $JSONL_PATH"
  echo
} > "$MD_PATH"

echo "Starting longrun checkpoints..."
echo "DURATION_SEC=$DURATION_SEC INTERVAL_SEC=$INTERVAL_SEC"
echo "Output JSONL: $JSONL_PATH"
echo "Output Markdown: $MD_PATH"
echo "Runtime metrics JSONL: $RUNTIME_METRICS_JSONL"
echo "Runtime metrics health report: $RUNTIME_METRICS_HEALTH_REPORT"
echo "ENABLE_RUNTIME_METRICS=$ENABLE_RUNTIME_METRICS"
echo "ENABLE_APPEND_RECORD=$ENABLE_APPEND_RECORD"
echo "START_WATCHERS=$START_WATCHERS"

if [[ "$START_WATCHERS" == "true" ]]; then
  echo "Launching runtime/ops/notify watchers..."
  ./.venv/bin/python -m auto_trader.runtime --watch --interval-sec 2 > "$OUTPUT_DIR/runtime_watch.log" 2>&1 &
  WATCHER_PIDS+=("$!")
  ./.venv/bin/python -m auto_trader.ops \
    --runtime-state-path data/runtime/control_state.json \
    --risk-eval-path data/risk/risk_eval.parquet \
    --watch --interval-sec 5 --output-dir data/ops > "$OUTPUT_DIR/ops_watch.log" 2>&1 &
  WATCHER_PIDS+=("$!")
  ./.venv/bin/python -m auto_trader.notify --from-env --watch --interval-sec 5 --output-dir data/ops > "$OUTPUT_DIR/notify_watch.log" 2>&1 &
  WATCHER_PIDS+=("$!")
  sleep 1
fi

while :; do
  now_epoch="$(date +%s)"
  if (( now_epoch > end_epoch )); then
    break
  fi

  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  checkpoint="$((checkpoint + 1))"

  runtime_updated_at="$(read_updated_at "$RUNTIME_STATE")"
  notify_updated_at="$(read_updated_at "$NOTIFY_STATE")"

  runtime_updated_progress="false"
  notify_updated_progress="false"
  [[ -n "$runtime_updated_at" && "$runtime_updated_at" != "$prev_runtime_updated_at" ]] && runtime_updated_progress="true"
  [[ -n "$notify_updated_at" && "$notify_updated_at" != "$prev_notify_updated_at" ]] && notify_updated_progress="true"

  runtime_lock_residual="false"
  notify_lock_residual="false"
  [[ -f "$RUNTIME_LOCK" ]] && runtime_lock_residual="true"
  [[ -f "$NOTIFY_LOCK" ]] && notify_lock_residual="true"

  runtime_bak_exists="false"
  notify_bak_exists="false"
  [[ -f "$RUNTIME_BAK" ]] && runtime_bak_exists="true"
  [[ -f "$NOTIFY_BAK" ]] && notify_bak_exists="true"

  runtime_bak_mtime="$(mtime_or_zero "$RUNTIME_BAK")"
  notify_bak_mtime="$(mtime_or_zero "$NOTIFY_BAK")"
  runtime_bak_progress="false"
  notify_bak_progress="false"
  [[ "$runtime_bak_mtime" -gt "$prev_runtime_bak_mtime" ]] && runtime_bak_progress="true"
  [[ "$notify_bak_mtime" -gt "$prev_notify_bak_mtime" ]] && notify_bak_progress="true"

  runtime_alive="$(proc_alive "$RUNTIME_PROC_PATTERN")"
  notify_alive="$(proc_alive "$NOTIFY_PROC_PATTERN")"
  ops_alive="$(proc_alive "$OPS_PROC_PATTERN")"

  if [[ "$ENABLE_RUNTIME_METRICS" == "true" ]]; then
    ./.venv/bin/python -m auto_trader.monitor \
      --runtime-state-path "$RUNTIME_STATE" \
      --gateway-state-path data/exchange/gateway_state.json \
      --risk-eval-path data/risk/risk_eval.parquet \
      --order-events-path data/exchange/order_events.jsonl \
      --output-jsonl "$RUNTIME_METRICS_JSONL" >/dev/null 2>&1 || true
  fi

  line="{\"checkpoint\":$checkpoint,\"checked_at\":\"$ts\",\
\"runtime_updated_at\":$(json_escape "$runtime_updated_at"),\
\"runtime_updated_progress\":$runtime_updated_progress,\
\"runtime_lock_residual\":$runtime_lock_residual,\
\"runtime_bak_exists\":$runtime_bak_exists,\
\"runtime_bak_progress\":$runtime_bak_progress,\
\"notify_updated_at\":$(json_escape "$notify_updated_at"),\
\"notify_updated_progress\":$notify_updated_progress,\
\"notify_lock_residual\":$notify_lock_residual,\
\"notify_bak_exists\":$notify_bak_exists,\
\"notify_bak_progress\":$notify_bak_progress,\
\"runtime_alive\":$runtime_alive,\
\"notify_alive\":$notify_alive,\
\"ops_alive\":$ops_alive}"
  echo "$line" >> "$JSONL_PATH"

  {
    echo "## checkpoint $checkpoint ($ts)"
    echo "- runtime updated_at progressed: $runtime_updated_progress"
    echo "- notify updated_at progressed: $notify_updated_progress"
    echo "- runtime lock residual: $runtime_lock_residual"
    echo "- notify lock residual: $notify_lock_residual"
    echo "- runtime bak exists/progress: $runtime_bak_exists / $runtime_bak_progress"
    echo "- notify bak exists/progress: $notify_bak_exists / $notify_bak_progress"
    echo "- watcher alive(runtime/notify/ops): $runtime_alive / $notify_alive / $ops_alive"
    echo
  } >> "$MD_PATH"

  prev_runtime_updated_at="$runtime_updated_at"
  prev_notify_updated_at="$notify_updated_at"
  prev_runtime_bak_mtime="$runtime_bak_mtime"
  prev_notify_bak_mtime="$notify_bak_mtime"

  sleep "$INTERVAL_SEC"
done

echo "Completed checkpoints: $checkpoint"

if [[ "$ENABLE_RUNTIME_METRICS" == "true" ]]; then
  if INPUT_PATH="$RUNTIME_METRICS_JSONL" \
    OUTPUT_PATH="$RUNTIME_METRICS_HEALTH_REPORT" \
    ./scripts/runtime_metrics_health_check.sh >/dev/null 2>&1; then
    echo "Runtime metrics health check: pass/warn"
  else
    echo "Runtime metrics health check: fail"
  fi
fi

if [[ "$ENABLE_APPEND_RECORD" == "true" ]]; then
  echo "Appending longrun summary record..."
  if [[ -n "$RECORD_PATH" ]]; then
    RECORD_PATH="$RECORD_PATH" \
      CHECKPOINTS_PATH="$JSONL_PATH" \
      HEALTH_REPORT_PATH="$RUNTIME_METRICS_HEALTH_REPORT" \
      ./scripts/append_longrun_record.sh || true
  else
    CHECKPOINTS_PATH="$JSONL_PATH" \
      HEALTH_REPORT_PATH="$RUNTIME_METRICS_HEALTH_REPORT" \
      ./scripts/append_longrun_record.sh || true
  fi
fi

echo "Artifacts:"
echo "  - $JSONL_PATH"
echo "  - $MD_PATH"
if [[ "$ENABLE_RUNTIME_METRICS" == "true" ]]; then
  echo "  - $RUNTIME_METRICS_JSONL"
  echo "  - $RUNTIME_METRICS_HEALTH_REPORT"
fi
if [[ "$START_WATCHERS" == "true" ]]; then
  echo "  - $OUTPUT_DIR/runtime_watch.log"
  echo "  - $OUTPUT_DIR/ops_watch.log"
  echo "  - $OUTPUT_DIR/notify_watch.log"
fi

python - "$JSONL_PATH" "$RUNTIME_METRICS_HEALTH_REPORT" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path


def load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    out: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return rec if isinstance(rec, dict) else {}


checkpoints = load_jsonl(Path(sys.argv[1]))
health = load_json(Path(sys.argv[2]))
import os
start_watchers = str(os.getenv("START_WATCHERS", "false")).lower() in {"1", "true", "yes", "on"}

runtime_lock_residual = any(bool(r.get("runtime_lock_residual", False)) for r in checkpoints)
notify_lock_residual = any(bool(r.get("notify_lock_residual", False)) for r in checkpoints)
runtime_alive_all = all(bool(r.get("runtime_alive", False)) for r in checkpoints) if checkpoints else False
ops_alive_all = all(bool(r.get("ops_alive", False)) for r in checkpoints) if checkpoints else False
notify_alive_all = all(bool(r.get("notify_alive", False)) for r in checkpoints) if checkpoints else False

# If watchers are not launched by this script, alive checks are informational only.
if not start_watchers:
    runtime_alive_all = True
    ops_alive_all = True
    notify_alive_all = True

health_status = str(health.get("overall_status", "unknown"))
if health_status == "fail" or runtime_lock_residual or notify_lock_residual or (not runtime_alive_all):
    overall = "NO_GO"
elif health_status == "warn" or (not ops_alive_all) or (not notify_alive_all):
    overall = "CONDITIONAL_GO"
else:
    overall = "GO"

print(
    "LONGRUN_SUMMARY "
    f"overall={overall} "
    f"health={health_status} "
    f"checkpoints={len(checkpoints)} "
    f"runtime_lock_residual_any={runtime_lock_residual} "
    f"notify_lock_residual_any={notify_lock_residual} "
    f"start_watchers={start_watchers} "
    f"runtime_alive_all={runtime_alive_all} "
    f"notify_alive_all={notify_alive_all} "
    f"ops_alive_all={ops_alive_all}"
)
PY
