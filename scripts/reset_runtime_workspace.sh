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

echo "== reset runtime workspace =="

"$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


root = Path(".")

# Safe runtime baseline: keep the file, but restart from Trading OFF.
runtime_dir = root / "data" / "runtime"
runtime_dir.mkdir(parents=True, exist_ok=True)
control_state_path = runtime_dir / "control_state.json"
for backup_path in (
    control_state_path.with_suffix(".json.bak"),
    runtime_dir / "worker_state.json.bak",
    runtime_dir / "gui_refresh_job.json.bak",
):
    backup_path.unlink(missing_ok=True)
control_state = {
    "trading_enabled": False,
    "emergency_stop": False,
    "close_all_requested": False,
    "updated_at": now_iso(),
}
control_state_path.write_text(json.dumps(control_state, ensure_ascii=True, indent=2), encoding="utf-8")

# Clear worker-derived state.
worker_state_path = runtime_dir / "worker_state.json"
worker_state = {
    "last_processed_bars": {},
    "last_results": {},
    "last_cycle_at": "",
    "last_error": "",
    "updated_at": "",
}
worker_state_path.write_text(json.dumps(worker_state, ensure_ascii=True, indent=2), encoding="utf-8")

control_cursor_path = runtime_dir / "control_cursor.json"
if control_cursor_path.exists():
    control_cursor_path.unlink()

gui_refresh_job_path = runtime_dir / "gui_refresh_job.json"
if gui_refresh_job_path.exists():
    gui_refresh_job_path.unlink()

# Clear local exchange/position residue.
exchange_dir = root / "data" / "exchange"
exchange_dir.mkdir(parents=True, exist_ok=True)
gateway_state_path = exchange_dir / "gateway_state.json"
gateway_state_path.with_suffix(".json.bak").unlink(missing_ok=True)
gateway_state = {
    "seen_client_ids": [],
    "pending_orders": {},
    "updated_at": now_iso(),
}
gateway_state_path.write_text(json.dumps(gateway_state, ensure_ascii=True, indent=2), encoding="utf-8")

order_events_path = exchange_dir / "order_events.jsonl"
order_events_path.write_text("", encoding="utf-8")

positions_dir = root / "data" / "positions"
positions_dir.mkdir(parents=True, exist_ok=True)
positions_path = positions_dir / "positions.parquet"
positions_path.with_suffix(".parquet.bak").unlink(missing_ok=True)
pd.DataFrame(
    columns=[
        "symbol",
        "strategy",
        "timeframe",
        "route_key",
        "side",
        "qty",
        "avg_entry",
        "unrealized_pnl_pct",
        "add_count",
        "updated_at",
    ]
).to_parquet(positions_path, index=False)

risk_dir = root / "data" / "risk"
risk_dir.mkdir(parents=True, exist_ok=True)
risk_input_path = risk_dir / "risk_input.parquet"
pd.DataFrame(
    columns=[
        "timestamp",
        "symbol",
        "current_equity",
        "equity_peak",
        "symbol_exposure_pct",
        "portfolio_exposure_pct",
        "concentration_score",
        "correlated_exposure_pct",
    ]
).to_parquet(risk_input_path, index=False)

risk_eval_path = risk_dir / "risk_eval.parquet"
pd.DataFrame(
    columns=[
        "timestamp",
        "symbol",
        "risk_blocked",
        "block_reason_codes",
        "current_dd_pct",
        "portfolio_exposure_pct",
        "concentration_score",
        "correlated_exposure_pct",
        "vol_weighted_exposure_pct",
        "risk_contribution_pct",
        "missing_vol_ratio",
        "size_scale",
        "emergency_state",
    ]
).to_parquet(risk_eval_path, index=False)

# Clear operational logs / rolling metrics.
clear_paths = [
    root / "data" / "validation" / "runtime_metrics.jsonl",
    root / "data" / "validation" / "runtime_watch.log",
    root / "data" / "validation" / "notify_watch.log",
    root / "data" / "validation" / "ops_watch.log",
    root / "data" / "ops" / "alerts.jsonl",
    root / "data" / "ops" / "notifications.jsonl",
]
for path in clear_paths:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")

summary = {
    "control_state_path": str(control_state_path),
    "worker_state_path": str(worker_state_path),
    "gateway_state_path": str(gateway_state_path),
    "order_events_path": str(order_events_path),
    "positions_path": str(positions_path),
    "risk_input_path": str(risk_input_path),
    "risk_eval_path": str(risk_eval_path),
    "cleared_logs": [str(path) for path in clear_paths],
}
print(json.dumps(summary, ensure_ascii=True, indent=2))
PY
