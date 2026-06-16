#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${OUT_DIR:-data/validation/chaos}"
mkdir -p "$OUT_DIR"

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
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

OHLCV_PATH="${OHLCV_PATH:-data/parquet/BTCUSDT_1m.parquet}"
SIGNALS_PATH="${SIGNALS_PATH:-data/signals/BTCUSDT_1m_range_signals.parquet}"
ML_PATH="${ML_PATH:-}"

RESULT_JSONL="$OUT_DIR/chaos_results.jsonl"
SUMMARY_JSON="$OUT_DIR/chaos_summary.json"

if [[ -n "$ML_PATH" ]]; then
  "$PYTHON_BIN" -m auto_trader.stress \
    --ohlcv-path "$OHLCV_PATH" \
    --signals-path "$SIGNALS_PATH" \
    --ml-path "$ML_PATH" \
    --output-dir "$OUT_DIR" >/dev/null
else
  "$PYTHON_BIN" -m auto_trader.stress \
    --ohlcv-path "$OHLCV_PATH" \
    --signals-path "$SIGNALS_PATH" \
    --output-dir "$OUT_DIR" >/dev/null
fi

"$PYTHON_BIN" - "$OUT_DIR/stress_results.parquet" "$RESULT_JSONL" "$SUMMARY_JSON" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

src = Path(sys.argv[1])
jsonl_path = Path(sys.argv[2])
summary_path = Path(sys.argv[3])
df = pd.read_parquet(src)

rows = []
for r in df.to_dict(orient="records"):
    rows.append(
        {
            "checked_at": datetime.now(UTC).isoformat(),
            "scenario_name": str(r.get("scenario_name", "")),
            "failure_count": int(float(r.get("failure_count", 0.0) or 0.0)),
            "stale_latency_max_sec": float(r.get("stale_latency_max_sec", 0.0) or 0.0),
            "stale_detect_to_stop_latency_sec": float(
                r.get("stale_detect_to_stop_latency_sec", 0.0) or 0.0
            ),
            "emergency_stop_triggered": bool(r.get("emergency_stop_triggered", False)),
            "pf": float(r.get("PF", 0.0) or 0.0),
            "max_dd": float(r.get("MaxDD", 0.0) or 0.0),
            "monthly_pnl": float(r.get("MonthlyPnL", 0.0) or 0.0),
        }
    )

jsonl_path.write_text(
    "".join(json.dumps(x, ensure_ascii=True) + "\n" for x in rows),
    encoding="utf-8",
)

partial_ok = any(
    x["scenario_name"] == "partial_fill_10pct_cancel" and x["failure_count"] == 0 for x in rows
)
silent_rows = [x for x in rows if x["scenario_name"] == "silent_ws_stale"]
silent_emergency = any(x["emergency_stop_triggered"] for x in silent_rows)
silent_detect_to_stop_latency = max(
    (x["stale_detect_to_stop_latency_sec"] for x in silent_rows), default=0.0
)

status = "pass" if partial_ok and silent_emergency else "warn"
summary = {
    "checked_at": datetime.now(UTC).isoformat(),
    "status": status,
    "checks": {
        "partial_fill_state_consistent": partial_ok,
        "silent_stale_emergency_triggered": silent_emergency,
        "silent_stale_detect_to_stop_latency_sec": silent_detect_to_stop_latency,
    },
    "result_jsonl": str(jsonl_path),
}
summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
print(summary_path)
PY

echo "done: $OUT_DIR"
