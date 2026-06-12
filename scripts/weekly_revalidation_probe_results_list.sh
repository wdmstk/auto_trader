#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${OUT_DIR:-data/validation/weekly_revalidation}"
REPORT_PATH="${REPORT_PATH:-$OUT_DIR/weekly_revalidation_report.json}"
OUT_PATH="${OUT_PATH:-$OUT_DIR/range_probe_result_list.md}"

mkdir -p "$(dirname "$OUT_PATH")"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python - "$REPORT_PATH" "$OUT_PATH" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

report_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])

if not report_path.exists():
    raise SystemExit(f"report not found: {report_path}")

report = json.loads(report_path.read_text(encoding="utf-8"))
probe_report = report.get("range_probe_candidates", {})

priority = {"core": 0, "probe": 1, "watchlist": 2}
note = {"core": "本線候補", "probe": "追加検証", "watchlist": "保留"}

def _collect_rows(payload: object) -> list[dict]:
    rows: list[dict] = []
    if isinstance(payload, dict):
        raw_rows = payload.get("rows", [])
        if isinstance(raw_rows, list):
            rows.extend(row for row in raw_rows if isinstance(row, dict))
        timeframe_reports = payload.get("timeframe_reports", [])
        if isinstance(timeframe_reports, list):
            for item in timeframe_reports:
                rows.extend(_collect_rows(item))
    elif isinstance(payload, list):
        for item in payload:
            rows.extend(_collect_rows(item))
    return rows

rows = _collect_rows(probe_report)
if not isinstance(probe_report, dict):
    probe_report = {}

unique_rows: list[dict] = []
seen_rows: set[tuple[str, str, str, str, float]] = set()
for row in rows:
    key = (
        str(row.get("symbol", "")).strip(),
        str(row.get("timeframe", "")).strip(),
        str(row.get("strategy", "")).strip(),
        str(row.get("candidate_status", "watchlist")).strip(),
        float(row.get("candidate_score", 0.0) or 0.0),
    )
    if key in seen_rows:
        continue
    seen_rows.add(key)
    unique_rows.append(row)

rows = sorted(
    unique_rows,
    key=lambda row: (
        priority.get(str(row.get("candidate_status", "watchlist")), 99),
        -float(row.get("candidate_score", 0.0) or 0.0),
        str(row.get("timeframe", "")),
        str(row.get("symbol", "")),
        str(row.get("strategy", "")),
    ),
)

timeframes: list[str] = []
if isinstance(report.get("range_probe_candidates"), dict):
    tf = report.get("range_probe_candidates", {}).get("timeframes", [])
    if isinstance(tf, list):
        timeframes = [str(x) for x in tf if str(x).strip()]
elif isinstance(report.get("range_probe_candidates"), list):
    seen_tf: set[str] = set()
    for item in report.get("range_probe_candidates", []):
        if not isinstance(item, dict):
            continue
        tf = str(item.get("timeframe", "")).strip()
        if tf and tf not in seen_tf:
            seen_tf.add(tf)
            timeframes.append(tf)

lines: list[str] = []
lines.append("# 週次再評価 Range Probe 結果一覧")
lines.append("")
lines.append(f"- generated_at: {datetime.now(UTC).isoformat()}")
lines.append(f"- report: {report_path}")
probe_status = "unknown"
if isinstance(report.get("range_probe_candidates"), dict):
    probe_status = str(report.get("range_probe_candidates", {}).get("status", "unknown"))
elif isinstance(report.get("range_probe_candidates"), list):
    statuses: list[str] = []
    for item in report.get("range_probe_candidates", []):
        if isinstance(item, dict):
            statuses.append(str(item.get("status", "unknown")))
    if statuses and all(status == "pass" for status in statuses):
        probe_status = "pass"
    elif any(status == "warn" for status in statuses):
        probe_status = "warn"
    elif statuses:
        probe_status = statuses[0]
lines.append(f"- probe_status: {probe_status}")
if timeframes:
    lines.append(f"- timeframes: {', '.join(str(x) for x in timeframes)}")
lines.append("")
lines.append("## Summary")
if isinstance(report.get("range_probe_candidates"), dict):
    route_counts = probe_report.get("route_counts", probe_report.get("candidate_counts", {}))
    if not isinstance(route_counts, dict):
        route_counts = {}
    lines.append(f"- core routes: {int(route_counts.get('core', 0) or 0)}")
    lines.append(f"- probe routes: {int(route_counts.get('probe', 0) or 0)}")
    lines.append(f"- watchlist routes: {int(route_counts.get('watchlist', 0) or 0)}")
else:
    core_count = sum(1 for row in rows if str(row.get("candidate_status", "")) == "core")
    probe_count = sum(1 for row in rows if str(row.get("candidate_status", "")) == "probe")
    watchlist_count = sum(1 for row in rows if str(row.get("candidate_status", "")) == "watchlist")
    lines.append(f"- core routes: {core_count}")
    lines.append(f"- probe routes: {probe_count}")
    lines.append(f"- watchlist routes: {watchlist_count}")
lines.append(f"- rows: {len(rows)}")
lines.append("")
lines.append("| Symbol | Status | Best TF | Strategy | PF | EXPbps | DD | Closed Trades | Score | Note |")
lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---|")

if rows:
    for row in rows:
        status = str(row.get("candidate_status", "watchlist"))
        lines.append(
            "| {symbol} | {status} | {timeframe} | {strategy} | {pf:.3f} | {exp:.2f} | {dd:.6f} | {ct:.2f} | {score:.2f} | {note} |".format(
                symbol=str(row.get("symbol", "")),
                status=status,
                timeframe=str(row.get("timeframe", "")),
                strategy=str(row.get("strategy", "")),
                pf=float(row.get("pf_mean", 0.0) or 0.0),
                exp=float(row.get("expectancy_bps_mean", 0.0) or 0.0),
                dd=float(row.get("max_dd_mean", 0.0) or 0.0),
                ct=float(row.get("closed_trades_mean", 0.0) or 0.0),
                score=float(row.get("candidate_score", 0.0) or 0.0),
                note=note.get(status, "保留"),
            )
        )
else:
    lines.append("| - | - | - | - | -: | -: | -: | -: | -: | probe candidates unavailable |")

out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(out_path)
PY
