#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${OUT_DIR:-data/validation/weekly_revalidation}"
REPORT_PATH="${REPORT_PATH:-$OUT_DIR/candidate_report.json}"
OUT_PATH="${OUT_PATH:-$OUT_DIR/result_list.md}"

mkdir -p "$(dirname "$OUT_PATH")"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python - "$REPORT_PATH" "$OUT_PATH" <<'PY'
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

report_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])

if not report_path.exists():
    raise SystemExit(f"report not found: {report_path}")

report = json.loads(report_path.read_text(encoding="utf-8"))
rows = [row for row in report.get("rows", []) if isinstance(row, dict)]

priority = {"core": 0, "probe": 1, "watchlist": 2}
note = {"core": "本線候補", "probe": "追加検証", "watchlist": "保留"}

by_symbol: dict[str, list[dict]] = defaultdict(list)
for row in rows:
    symbol = str(row.get("symbol", "")).strip()
    if symbol:
        by_symbol[symbol].append(row)

def best_row(items: list[dict]) -> dict:
    return min(
        items,
        key=lambda row: (
            priority.get(str(row.get("candidate_status", "watchlist")), 99),
            -float(row.get("candidate_score", 0.0) or 0.0),
            str(row.get("timeframe", "")),
            str(row.get("strategy", "")),
        ),
    )

symbols = sorted(
    by_symbol,
    key=lambda symbol: (
        priority.get(str(best_row(by_symbol[symbol]).get("candidate_status", "watchlist")), 99),
        -float(best_row(by_symbol[symbol]).get("candidate_score", 0.0) or 0.0),
        symbol,
    ),
)

lines: list[str] = []
lines.append("# 週次再評価 結果一覧")
lines.append("")
lines.append(f"- generated_at: {datetime.now(UTC).isoformat()}")
lines.append(f"- report: {report_path}")
lines.append(f"- status: {report.get('status', 'unknown')}")
timeframes = report.get("timeframes", [])
if isinstance(timeframes, list) and timeframes:
    lines.append(f"- timeframes: {', '.join(str(x) for x in timeframes)}")
lines.append("")
lines.append("## Summary")
route_counts = report.get("route_counts", report.get("candidate_counts", {}))
symbol_counts = report.get("symbol_counts", {})
if not isinstance(route_counts, dict):
    route_counts = {}
if not isinstance(symbol_counts, dict):
    symbol_counts = {}
lines.append(f"- core routes: {int(route_counts.get('core', 0) or 0)}")
lines.append(f"- probe routes: {int(route_counts.get('probe', 0) or 0)}")
lines.append(f"- watchlist routes: {int(route_counts.get('watchlist', 0) or 0)}")
lines.append(f"- symbols: {len(symbols)}")
lines.append("")
lines.append("| Symbol | Status | Best TF | Strategy | PF | EXPbps | DD | Closed Trades | Score | Shadow Routes | Note |")
lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---|---|")

for symbol in symbols:
    best = best_row(by_symbol[symbol])
    status = str(best.get("candidate_status", "watchlist"))
    shadows = [
        f"{row.get('strategy','')}/{row.get('timeframe','')}/{row.get('candidate_status','')}"
        for row in by_symbol[symbol]
        if row is not best
    ]
    lines.append(
        "| {symbol} | {status} | {timeframe} | {strategy} | {pf:.3f} | {exp:.2f} | {dd:.6f} | {ct:.2f} | {score:.2f} | {shadows} | {note} |".format(
            symbol=symbol,
            status=status,
            timeframe=str(best.get("timeframe", "")),
            strategy=str(best.get("strategy", "")),
            pf=float(best.get("pf_mean", 0.0) or 0.0),
            exp=float(best.get("expectancy_bps_mean", 0.0) or 0.0),
            dd=float(best.get("max_dd_mean", 0.0) or 0.0),
            ct=float(best.get("closed_trades_mean", 0.0) or 0.0),
            score=float(best.get("candidate_score", 0.0) or 0.0),
            shadows=", ".join(shadows) if shadows else "-",
            note=note.get(status, "保留"),
        )
    )

out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(out_path)
PY
