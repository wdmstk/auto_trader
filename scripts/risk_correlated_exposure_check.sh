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
OUTPUT_DIR="${OUTPUT_DIR:-data/validation}"
INPUT_PATH="${INPUT_PATH:-$OUTPUT_DIR/risk_corr_scenario_input.parquet}"
EVAL_PATH="${EVAL_PATH:-$OUTPUT_DIR/risk_corr_scenario_eval.parquet}"
SUMMARY_PATH="${SUMMARY_PATH:-$OUTPUT_DIR/risk_corr_scenario_summary.json}"
THRESHOLD="${THRESHOLD:-30}"

mkdir -p "$OUTPUT_DIR"

echo "== correlated exposure risk check =="
echo "input=$INPUT_PATH eval=$EVAL_PATH threshold=$THRESHOLD"

"$PYTHON_BIN" - "$INPUT_PATH" <<'PY'
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

path = Path(sys.argv[1])
base = datetime(2026, 1, 1, tzinfo=UTC)
rows = [
    {
        "timestamp": base,
        "symbol": "BTCUSDT",
        "current_equity": 10000.0,
        "equity_peak": 10000.0,
        "symbol_exposure_pct": 8.0,
        "portfolio_exposure_pct": 20.0,
        "concentration_score": 0.3,
        "correlated_exposure_pct": 12.0,
    },
    {
        "timestamp": base + timedelta(minutes=1),
        "symbol": "BTCUSDT",
        "current_equity": 10000.0,
        "equity_peak": 10000.0,
        "symbol_exposure_pct": 8.0,
        "portfolio_exposure_pct": 20.0,
        "concentration_score": 0.3,
        "correlated_exposure_pct": 65.0,
    },
]
path.parent.mkdir(parents=True, exist_ok=True)
pd.DataFrame(rows).to_parquet(path, index=False)
print(f"rows={len(rows)}")
PY

"$PYTHON_BIN" -m auto_trader.risk \
  --input-path "$INPUT_PATH" \
  --output-path "$EVAL_PATH" \
  --max-correlated-exposure-pct "$THRESHOLD"

"$PYTHON_BIN" - "$EVAL_PATH" "$SUMMARY_PATH" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

eval_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
df = pd.read_parquet(eval_path)
blocked = df[df["risk_blocked"] == True]  # noqa: E712
reasons = []
if not blocked.empty:
    for v in blocked["block_reason_codes"].tolist():
        if hasattr(v, "tolist"):
            reasons.append(v.tolist())
        elif isinstance(v, list):
            reasons.append(v)
        else:
            reasons.append([str(v)])
summary = {
    "rows": int(len(df)),
    "blocked_rows": int(len(blocked)),
    "blocked_reasons": reasons,
}
summary_path.write_text(json.dumps(summary, ensure_ascii=True), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=True))
PY

echo "summary: $SUMMARY_PATH"
