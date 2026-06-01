#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
INPUT_PATH="${INPUT_PATH:-data/risk/risk_input.parquet}"
OUTPUT_PATH="${OUTPUT_PATH:-data/risk/risk_input.parquet}"

echo "== enrich risk_input with correlated_exposure_pct =="
echo "input=$INPUT_PATH output=$OUTPUT_PATH"

"$PYTHON_BIN" - "$INPUT_PATH" "$OUTPUT_PATH" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

input_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])

df = pd.read_parquet(input_path)
if "correlated_exposure_pct" not in df.columns:
    # 1) Prefer explicit cluster columns if present.
    corr_cols = [c for c in df.columns if c.endswith("_corr_exposure_pct")]
    if corr_cols:
        df["correlated_exposure_pct"] = df[corr_cols].max(axis=1).fillna(0.0)
    # 2) Fallback proxy: portfolio exposure weighted by concentration.
    elif {"portfolio_exposure_pct", "concentration_score"}.issubset(df.columns):
        df["correlated_exposure_pct"] = (
            pd.to_numeric(df["portfolio_exposure_pct"], errors="coerce").fillna(0.0)
            * pd.to_numeric(df["concentration_score"], errors="coerce").fillna(0.0)
        )
    else:
        df["correlated_exposure_pct"] = 0.0

output_path.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(output_path, index=False)
print(f"rows={len(df)} min={float(df['correlated_exposure_pct'].min()):.4f} max={float(df['correlated_exposure_pct'].max()):.4f}")
PY
