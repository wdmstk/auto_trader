#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

ROUTES="${ROUTES:-}"
OUT_PATH="${OUT_PATH:-data/validation/core_expansion/fold_breakdown.md}"
DATA_ROOT="${DATA_ROOT:-data}"
ANALYSIS_DIR="${ANALYSIS_DIR:-$DATA_ROOT/analysis}"

mkdir -p "$(dirname "$OUT_PATH")"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python - "$ROUTES" "$OUT_PATH" "$ANALYSIS_DIR" "$DATA_ROOT" <<'PY'
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

routes_arg = sys.argv[1]
out_path = Path(sys.argv[2])
analysis_dir = Path(sys.argv[3])
data_root = Path(sys.argv[4])

routes = [item.strip() for item in routes_arg.split(",") if item.strip()]
if not routes:
    raise SystemExit("ROUTES is required")

lines: list[str] = []
lines.append("# Walkforward Fold Breakdown")
lines.append("")
lines.append(f"- generated_at: {datetime.now(UTC).isoformat()}")
lines.append(f"- data_root: {data_root}")
lines.append(f"- analysis_dir: {analysis_dir}")
lines.append("")

for route in routes:
    try:
        strategy, symbol, timeframe = route.split(":")
    except ValueError as exc:
        raise SystemExit(f"invalid route format: {route}") from exc
    summary_path = analysis_dir / f"walkforward_{symbol}_{timeframe}_{strategy}_summary.parquet"
    lines.append(f"## {route}")
    lines.append("")
    if not summary_path.exists():
        lines.append(f"- status: missing_summary")
        lines.append(f"- path: {summary_path}")
        lines.append("")
        continue

    df = pd.read_parquet(summary_path).copy()
    if df.empty:
        lines.append(f"- status: empty_summary")
        lines.append(f"- path: {summary_path}")
        lines.append("")
        continue

    totals = {
        "closed_trades": float(df["closed_trades"].sum()) if "closed_trades" in df.columns else 0.0,
        "entries": float(df["entries"].sum()) if "entries" in df.columns else 0.0,
        "period_pnl": float(df["period_pnl"].sum()) if "period_pnl" in df.columns else 0.0,
        "gross_pnl_est": float(df["gross_pnl_est"].sum()) if "gross_pnl_est" in df.columns else 0.0,
        "total_cost_est": float(df["total_cost_est"].sum()) if "total_cost_est" in df.columns else 0.0,
    }
    worst_fold = None
    if "period_pnl" in df.columns and not df["period_pnl"].empty:
        worst_fold = int(df.sort_values("period_pnl", ascending=True).iloc[0]["fold"])

    lines.append(f"- summary_path: {summary_path}")
    lines.append(f"- total_entries: {totals['entries']:.0f}")
    lines.append(f"- total_closed_trades: {totals['closed_trades']:.0f}")
    lines.append(f"- total_period_pnl: {totals['period_pnl']:.3f}")
    lines.append(f"- total_gross_pnl_est: {totals['gross_pnl_est']:.3f}")
    lines.append(f"- total_cost_est: {totals['total_cost_est']:.3f}")
    if totals["gross_pnl_est"] != 0:
        lines.append(f"- cost_to_gross_ratio: {totals['total_cost_est'] / abs(totals['gross_pnl_est']):.3f}")
    if worst_fold is not None:
        lines.append(f"- worst_fold: {worst_fold}")
    lines.append("")
    lines.append("| Fold | Entries | Closed Trades | PF | EXPbps | PeriodPnL | DD | GrossPnL | Cost |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for _, row in df.sort_values("fold").iterrows():
        lines.append(
            "| {fold:.0f} | {entries:.0f} | {closed_trades:.0f} | {pf:.3f} | {expbps:.2f} | {pnl:.3f} | {dd:.5f} | {gross:.3f} | {cost:.3f} |".format(
                fold=float(row.get("fold", 0) or 0),
                entries=float(row.get("entries", 0) or 0),
                closed_trades=float(row.get("closed_trades", 0) or 0),
                pf=float(row.get("pf", 0) or 0),
                expbps=float(row.get("expectancy_bps", 0) or 0),
                pnl=float(row.get("period_pnl", 0) or 0),
                dd=float(row.get("max_dd", 0) or 0),
                gross=float(row.get("gross_pnl_est", 0) or 0),
                cost=float(row.get("total_cost_est", 0) or 0),
            )
        )
    lines.append("")

out_path.write_text("\n".join(lines), encoding="utf-8")
print(out_path)
PY
