#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

REPORT_PATH="${REPORT_PATH:-data/validation/symbol_candidate_exploration/timeframe_scan/candidate_report.json}"
MANIFEST_PATH="${MANIFEST_PATH:-data/validation/symbol_candidate_exploration/symbol_exploration_manifest.json}"
OUT_PATH="${OUT_PATH:-data/validation/symbol_candidate_exploration/result_list.md}"

mkdir -p "$(dirname "$OUT_PATH")"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python - "$REPORT_PATH" "$MANIFEST_PATH" "$OUT_PATH" <<'PY'
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, UTC
from pathlib import Path

report_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
out_path = Path(sys.argv[3])

if not report_path.exists():
    raise SystemExit(f"report not found: {report_path}")

report = json.loads(report_path.read_text(encoding="utf-8"))
manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

rows = [row for row in report.get("rows", []) if isinstance(row, dict)]
priority = {"core": 0, "probe": 1, "watchlist": 2}
note = {"core": "本線候補", "probe": "追加検証", "watchlist": "保留"}

by_symbol: dict[str, list[dict]] = defaultdict(list)
for row in rows:
    symbol = str(row.get("symbol", "")).strip()
    if symbol:
        by_symbol[symbol].append(row)

selected_symbols = manifest.get("selected_symbols", [])
selected_set = {str(x).strip() for x in selected_symbols if str(x).strip()}
if selected_set:
    symbols = [sym for sym in by_symbol if sym in selected_set]
else:
    symbols = list(by_symbol.keys())

def sort_key(symbol: str) -> tuple[int, float, str]:
    items = by_symbol[symbol]
    best = min(
        items,
        key=lambda row: (
            priority.get(str(row.get("candidate_status", "watchlist")), 99),
            -float(row.get("candidate_score", 0.0) or 0.0),
            str(row.get("timeframe", "")),
            str(row.get("strategy", "")),
        ),
    )
    return (
        priority.get(str(best.get("candidate_status", "watchlist")), 99),
        -float(best.get("candidate_score", 0.0) or 0.0),
        symbol,
    )

symbols = sorted(symbols, key=sort_key)

lines: list[str] = []
lines.append("# 新規銘柄探索 結果一覧")
lines.append("")
lines.append(f"- generated_at: {datetime.now(UTC).isoformat()}")
lines.append(f"- report: {report_path}")
if manifest_path.exists():
    lines.append(f"- manifest: {manifest_path}")
lines.append(f"- status: {report.get('status', 'unknown')}")
lines.append("")
lines.append("## Summary")
lines.append(f"- core: {len(report.get('core_symbols', []))}")
lines.append(f"- probe: {len(report.get('probe_symbols', []))}")
lines.append(f"- watchlist: {len(report.get('watchlist_symbols', []))}")
lines.append(f"- rows: {len(symbols)}")
lines.append("")
lines.append("| Symbol | Status | Best TF | Strategy | PF | EXPbps | DD | Closed Trades | Score | Note |")
lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---|")

for symbol in symbols:
    items = by_symbol[symbol]
    best = min(
        items,
        key=lambda row: (
            priority.get(str(row.get("candidate_status", "watchlist")), 99),
            -float(row.get("candidate_score", 0.0) or 0.0),
            str(row.get("timeframe", "")),
            str(row.get("strategy", "")),
        ),
    )
    status = str(best.get("candidate_status", "watchlist"))
    lines.append(
        "| {symbol} | {status} | {timeframe} | {strategy} | {pf:.3f} | {exp:.2f} | {dd:.6f} | {ct:.2f} | {score:.2f} | {note} |".format(
            symbol=symbol,
            status=status,
            timeframe=str(best.get("timeframe", "")),
            strategy=str(best.get("strategy", "")),
            pf=float(best.get("pf_mean", 0.0) or 0.0),
            exp=float(best.get("expectancy_bps_mean", 0.0) or 0.0),
            dd=float(best.get("max_dd_mean", 0.0) or 0.0),
            ct=float(best.get("closed_trades_mean", 0.0) or 0.0),
            score=float(best.get("candidate_score", 0.0) or 0.0),
            note=note.get(status, "保留"),
        )
    )

out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(out_path)
PY
