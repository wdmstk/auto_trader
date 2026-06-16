#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
REPORT_PATH="${REPORT_PATH:-data/validation/weekly_autotune/weekly_revalidation/weekly_revalidation_report.json}"
OUT_PATH="${OUT_PATH:-data/validation/weekly_autotune/weekly_revalidation/portfolio_next_action_report.md}"

mkdir -p "$(dirname "$OUT_PATH")"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
"$PYTHON_BIN" - "$REPORT_PATH" "$OUT_PATH" <<'PY'
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
overview = report.get("overview", {})
if not isinstance(overview, dict):
    overview = {}
route_quality = report.get("route_quality_audit", {})
if not isinstance(route_quality, dict):
    route_quality = {}
if not route_quality:
    fallback_route_quality = overview.get("route_quality_audit", {})
    if isinstance(fallback_route_quality, dict):
        route_quality = fallback_route_quality
pq = overview.get("portfolio_qualification_summary", {})
if not isinstance(pq, dict):
    pq = {}
gap = overview.get("portfolio_qualification_gap_summary", {})
if not isinstance(gap, dict):
    gap = {}
next_action = overview.get("portfolio_next_action_summary", {})
if not isinstance(next_action, dict):
    next_action = {}
priority = overview.get("portfolio_next_action_route_keys", [])
if not isinstance(priority, list):
    priority = []
statistical = report.get("statistical_qualification", {})
if not isinstance(statistical, dict):
    statistical = {}
route_results = statistical.get("routes", [])
if not isinstance(route_results, list):
    route_results = []
route_actions = route_quality.get("route_actions", [])
if not isinstance(route_actions, list):
    route_actions = []

route_action_by_key: dict[str, dict[str, object]] = {}
for action in route_actions:
    if not isinstance(action, dict):
        continue
    route_key = str(action.get("route_key", "")).strip()
    if route_key:
        route_action_by_key[route_key] = action

route_coverage: list[dict[str, object]] = []
for route in route_results:
    if not isinstance(route, dict):
        continue
    route_key = str(route.get("route_key", "")).strip()
    strategy = str(route.get("strategy", "")).strip()
    if not strategy and ":" in route_key:
        strategy = route_key.split(":", 1)[0].strip()
    metrics = route.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    closed_trades = int(float(metrics.get("closed_trades", 0) or 0))
    action = route_action_by_key.get(route_key, {})
    recommendation = str(action.get("recommendation", "")).strip() if isinstance(action, dict) else ""
    if not recommendation:
        recommendation = "monitor" if str(route.get("status", "")).strip() == "pass" else "drop_or_retune"
    route_coverage.append(
        {
            "route_key": route_key,
            "strategy": strategy,
            "status": str(route.get("status", "")).strip(),
            "recommendation": recommendation,
            "closed_trades": closed_trades,
            "gap_to_30": max(0, 30 - closed_trades),
            "gap_to_100": max(0, 100 - closed_trades),
        }
    )

route_priority_order = {"accumulate_oos": 0, "monitor": 1, "drop_or_retune": 2}
route_coverage.sort(
    key=lambda item: (
        route_priority_order.get(str(item.get("recommendation", "")), 99),
        -int(item.get("gap_to_30", 0) or 0),
        str(item.get("route_key", "")),
    )
)

lines: list[str] = []
lines.append("# Portfolio Next Action Report")
lines.append("")
lines.append(f"- generated_at: {datetime.now(UTC).isoformat()}")
lines.append(f"- report: {report_path}")
lines.append(f"- portfolio_status: {pq.get('status', 'unknown')}")
lines.append(f"- required_route_count: {int(pq.get('required_route_count', 0) or 0)}")
lines.append(f"- required_strategy_count: {int(pq.get('required_strategy_count', 0) or 0)}")
lines.append(f"- missing_route_count: {int(pq.get('missing_route_count', 0) or 0)}")
lines.append(f"- missing_strategy_count: {int(pq.get('missing_strategy_count', 0) or 0)}")
if priority:
    lines.append(f"- next_route_keys: {', '.join(str(key) for key in priority)}")
lines.append("")
required_route_count = int(gap.get("required_route_count", pq.get("required_route_count", 0)) or 0)
required_strategy_count = int(gap.get("required_strategy_count", pq.get("required_strategy_count", 0)) or 0)
qualified_route_count = int(pq.get("qualified_route_count", 0) or 0)
qualified_strategy_count = int(pq.get("qualified_strategy_count", 0) or 0)
lines.append("## Qualification")
lines.append(f"- selected_route_keys: {', '.join(str(v) for v in pq.get('selected_route_keys', [])) if pq.get('selected_route_keys') else '-'}")
lines.append(f"- qualified_route_keys: {', '.join(str(v) for v in pq.get('qualified_route_keys', [])) if pq.get('qualified_route_keys') else '-'}")
lines.append(f"- selected_strategy_keys: {', '.join(str(v) for v in pq.get('selected_strategy_keys', [])) if pq.get('selected_strategy_keys') else '-'}")
lines.append(f"- qualified_strategy_keys: {', '.join(str(v) for v in pq.get('qualified_strategy_keys', [])) if pq.get('qualified_strategy_keys') else '-'}")
lines.append(f"- reasons: {', '.join(str(v) for v in pq.get('reasons', [])) if pq.get('reasons') else '-'}")
lines.append(f"- pass_path: need {required_route_count} qualified routes across {required_strategy_count} strategies")
lines.append("")
lines.append("## Pass Gaps")
lines.append(f"- route_gap_to_pass: {max(0, required_route_count - qualified_route_count)}")
lines.append(f"- strategy_gap_to_pass: {max(0, required_strategy_count - qualified_strategy_count)}")
lines.append(f"- remaining_selected_routes: {len(pq.get('selected_route_keys', []) if isinstance(pq.get('selected_route_keys', []), list) else [])}")
lines.append(f"- remaining_selected_strategies: {len(pq.get('selected_strategy_keys', []) if isinstance(pq.get('selected_strategy_keys', []), list) else [])}")
lines.append("")
lines.append("## Gap")
if isinstance(gap.get('next_route_keys', []), list) and gap.get('next_route_keys'):
    lines.append(f"- gap_next_route_keys: {', '.join(str(v) for v in gap.get('next_route_keys', []))}")
lines.append("")
lines.append("## Strategy Actions")
lines.append("| Strategy | Selected | Qualified | Recommendation | Sample Thin | OOS Quality | Accumulate OOS | Drop/Retune |")
lines.append("|---|---:|---:|---|---:|---:|---|---|")
for strategy, item in next_action.items():
    if not isinstance(item, dict):
        continue
    acc = item.get("accumulate_oos_route_keys", [])
    dr = item.get("drop_or_retune_route_keys", [])
    lines.append(
        "| {strategy} | {selected} | {qualified} | {recommendation} | {sample_thin} | {oos_quality} | {acc} | {dr} |".format(
            strategy=strategy,
            selected=int(item.get("selected_route_count", 0) or 0),
            qualified=int(item.get("qualified_route_count", 0) or 0),
            recommendation=str(item.get("recommendation", "")),
            sample_thin=int(item.get("sample_thin_count", 0) or 0),
            oos_quality=int(item.get("oos_quality_count", 0) or 0),
            acc=", ".join(str(v) for v in acc) if isinstance(acc, list) and acc else "-",
            dr=", ".join(str(v) for v in dr) if isinstance(dr, list) and dr else "-",
        )
    )

lines.append("")
lines.append("## Route Coverage")
lines.append("| Route | Strategy | Status | Recommendation | Closed Trades | Gap To 30 | Gap To 100 |")
lines.append("|---|---|---|---|---:|---:|---:|")
for item in route_coverage:
    if not isinstance(item, dict):
        continue
    lines.append(
        "| {route_key} | {strategy} | {status} | {recommendation} | {closed} | {gap_30} | {gap_100} |".format(
            route_key=str(item.get("route_key", "")),
            strategy=str(item.get("strategy", "")),
            status=str(item.get("status", "")),
            recommendation=str(item.get("recommendation", "")),
            closed=int(item.get("closed_trades", 0) or 0),
            gap_30=int(item.get("gap_to_30", 0) or 0),
            gap_100=int(item.get("gap_to_100", 0) or 0),
        )
    )

out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(out_path)
PY
