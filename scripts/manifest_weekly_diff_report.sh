#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
MANIFEST_PATH="${MANIFEST_PATH:-data/validation/weekly_autotune/manifest/route_selection_manifest.json}"
WEEKLY_SUMMARY_PATH="${WEEKLY_SUMMARY_PATH:-data/validation/weekly_autotune/weekly_revalidation/manifest_route_summary.json}"
WEEKLY_CANDIDATE_PATH="${WEEKLY_CANDIDATE_PATH:-data/validation/weekly_autotune/weekly_revalidation/manifest_candidate_report.json}"
WEEKLY_REPORT_PATH="${WEEKLY_REPORT_PATH:-data/validation/weekly_autotune/weekly_revalidation/weekly_revalidation_report.json}"
STATISTICAL_REPORT_PATH="${STATISTICAL_REPORT_PATH:-data/validation/statistical_qualification/qualification_report.json}"
OUTPUT_JSON="${OUTPUT_JSON:-data/validation/weekly_autotune/weekly_revalidation/manifest_vs_weekly_diff.json}"
OUTPUT_MD="${OUTPUT_MD:-data/validation/weekly_autotune/weekly_revalidation/manifest_vs_weekly_diff.md}"

"$PYTHON_BIN" - "$MANIFEST_PATH" "$WEEKLY_SUMMARY_PATH" "$WEEKLY_CANDIDATE_PATH" "$WEEKLY_REPORT_PATH" "$STATISTICAL_REPORT_PATH" "$OUTPUT_JSON" "$OUTPUT_MD" <<'PY'
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def route_key(row: dict[str, object]) -> str:
    return f"{row.get('strategy','')}:{row.get('symbol','')}:{row.get('timeframe','')}"


def load_json(path_str: str) -> dict[str, object]:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def num(value: object) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


manifest = load_json(Path(__import__("sys").argv[1]).as_posix())
weekly_summary = load_json(Path(__import__("sys").argv[2]).as_posix())
weekly_candidate = load_json(Path(__import__("sys").argv[3]).as_posix())
weekly_report = load_json(Path(__import__("sys").argv[4]).as_posix())
statistical = load_json(Path(__import__("sys").argv[5]).as_posix())
output_json = Path(__import__("sys").argv[6])
output_md = Path(__import__("sys").argv[7])

manifest_routes = manifest.get("selection", {}).get("trade_routes", [])
manifest_routes = manifest_routes if isinstance(manifest_routes, list) else []
summary_rows = weekly_summary.get("rows", [])
summary_rows = summary_rows if isinstance(summary_rows, list) else []
candidate_rows = weekly_candidate.get("rows", [])
candidate_rows = candidate_rows if isinstance(candidate_rows, list) else []
selected_routes = weekly_report.get("selection", {}).get("trade_routes", [])
selected_routes = selected_routes if isinstance(selected_routes, list) else []
stat_routes = statistical.get("routes", [])
stat_routes = stat_routes if isinstance(stat_routes, list) else []

summary_by_key = {route_key(row): row for row in summary_rows if isinstance(row, dict)}
candidate_by_key = {route_key(row): row for row in candidate_rows if isinstance(row, dict)}
selected_by_key = {route_key(row): row for row in selected_routes if isinstance(row, dict)}
stat_by_key = {str(row.get("route_key", "")): row for row in stat_routes if isinstance(row, dict)}

rows: list[dict[str, object]] = []
for raw in manifest_routes:
    if not isinstance(raw, dict):
        continue
    key = route_key(raw)
    weekly_row = summary_by_key.get(key, {})
    candidate_row = candidate_by_key.get(key, {})
    selected_row = selected_by_key.get(key, {})
    stat_row = stat_by_key.get(key, {})
    rows.append(
        {
            "route_key": key,
            "strategy": raw.get("strategy", ""),
            "symbol": raw.get("symbol", ""),
            "timeframe": raw.get("timeframe", ""),
            "selected_stage": raw.get("selected_stage", ""),
            "params": raw.get("params", {}),
            "manifest": {
                "candidate_status": raw.get("candidate_status", ""),
                "statistical_status": raw.get("statistical_status", ""),
                "pf_mean": num(raw.get("pf_mean", 0.0)),
                "expectancy_bps_mean": num(raw.get("expectancy_bps_mean", 0.0)),
                "period_pnl_mean": num(raw.get("period_pnl_mean", 0.0)),
                "max_dd_mean": num(raw.get("max_dd_mean", 0.0)),
                "closed_trades_mean": num(raw.get("closed_trades_mean", 0.0)),
            },
            "weekly": {
                "candidate_status": candidate_row.get("candidate_status", ""),
                "selected_in_weekly_report": bool(selected_row),
                "statistical_status": selected_row.get("statistical_status", stat_row.get("status", "")),
                "pf_mean": num(weekly_row.get("pf_mean", 0.0)),
                "expectancy_bps_mean": num(weekly_row.get("expectancy_bps_mean", 0.0)),
                "period_pnl_mean": num(weekly_row.get("period_pnl_mean", 0.0)),
                "max_dd_mean": num(weekly_row.get("max_dd_mean", 0.0)),
                "closed_trades_mean": num(weekly_row.get("closed_trades_mean", 0.0)),
                "statistical_reasons": stat_row.get("reasons", []),
            },
            "delta": {
                "pf_mean": num(weekly_row.get("pf_mean", 0.0)) - num(raw.get("pf_mean", 0.0)),
                "expectancy_bps_mean": num(weekly_row.get("expectancy_bps_mean", 0.0)) - num(raw.get("expectancy_bps_mean", 0.0)),
                "period_pnl_mean": num(weekly_row.get("period_pnl_mean", 0.0)) - num(raw.get("period_pnl_mean", 0.0)),
                "max_dd_mean": num(weekly_row.get("max_dd_mean", 0.0)) - num(raw.get("max_dd_mean", 0.0)),
                "closed_trades_mean": num(weekly_row.get("closed_trades_mean", 0.0)) - num(raw.get("closed_trades_mean", 0.0)),
            },
        }
    )

payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "manifest_path": str(Path(__import__("sys").argv[1])),
    "weekly_summary_path": str(Path(__import__("sys").argv[2])),
    "weekly_candidate_path": str(Path(__import__("sys").argv[3])),
    "weekly_report_path": str(Path(__import__("sys").argv[4])),
    "statistical_report_path": str(Path(__import__("sys").argv[5])),
    "route_count": len(rows),
    "rows": rows,
}
output_json.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines = [
    "# Manifest vs Weekly Diff",
    "",
    f"- generated_at: {payload['generated_at']}",
    f"- route_count: {len(rows)}",
    f"- manifest_path: {payload['manifest_path']}",
    f"- weekly_summary_path: {payload['weekly_summary_path']}",
    "",
    "| Route | Stage | Manifest PF | Weekly PF | dPF | Manifest EXPbps | Weekly EXPbps | dEXP | Manifest PnL | Weekly PnL | dPnL | Manifest Trades | Weekly Trades | dTrades | Weekly Candidate | Weekly Statistical | In Weekly Selection |",
    "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
]
for row in rows:
    m = row["manifest"]
    w = row["weekly"]
    d = row["delta"]
    lines.append(
        f"| {row['route_key']} | {row['selected_stage']} | "
        f"{m['pf_mean']:.3f} | {w['pf_mean']:.3f} | {d['pf_mean']:+.3f} | "
        f"{m['expectancy_bps_mean']:.2f} | {w['expectancy_bps_mean']:.2f} | {d['expectancy_bps_mean']:+.2f} | "
        f"{m['period_pnl_mean']:.3f} | {w['period_pnl_mean']:.3f} | {d['period_pnl_mean']:+.3f} | "
        f"{m['closed_trades_mean']:.2f} | {w['closed_trades_mean']:.2f} | {d['closed_trades_mean']:+.2f} | "
        f"{w['candidate_status']} | {w['statistical_status']} | {'yes' if w['selected_in_weekly_report'] else 'no'} |"
    )
lines.extend(["", "## Statistical Reasons", ""])
for row in rows:
    reasons = row["weekly"]["statistical_reasons"]
    lines.append(f"### {row['route_key']}")
    lines.append("")
    lines.append(f"- weekly_candidate_status: {row['weekly']['candidate_status']}")
    lines.append(f"- weekly_statistical_status: {row['weekly']['statistical_status']}")
    lines.append(f"- selected_in_weekly_report: {'yes' if row['weekly']['selected_in_weekly_report'] else 'no'}")
    lines.append(f"- reasons: {', '.join(str(x) for x in reasons) if reasons else '-'}")
    lines.append("")

output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(output_json)
print(output_md)
PY
