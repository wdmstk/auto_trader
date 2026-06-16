#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
REPORT_PATH="${REPORT_PATH:-data/validation/weekly_autotune/weekly_revalidation/weekly_revalidation_report.json}"
OUT_PATH="${OUT_PATH:-data/validation/weekly_autotune/weekly_revalidation/strategy_quality_report.md}"

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
output_format = out_path.suffix.lower().lstrip(".")
if output_format not in {"md", "json"}:
    output_format = "md"

if not report_path.exists():
    raise SystemExit(f"report not found: {report_path}")

report = json.loads(report_path.read_text(encoding="utf-8"))
overview = report.get("overview", {})
if not isinstance(overview, dict):
    overview = {}
statistical = report.get("statistical_qualification", {})
if not isinstance(statistical, dict):
    statistical = {}
route_quality = report.get("route_quality_audit", {})
if not isinstance(route_quality, dict):
    route_quality = {}
if not route_quality:
    fallback_route_quality = overview.get("route_quality_audit", {})
    if isinstance(fallback_route_quality, dict):
        route_quality = fallback_route_quality
strategy_quality = overview.get("strategy_quality_summary", {})
if not isinstance(strategy_quality, dict):
    strategy_quality = {}
strategy_priority = overview.get("portfolio_strategy_priority_summary", {})
if not isinstance(strategy_priority, dict):
    strategy_priority = {}
next_action = overview.get("portfolio_next_action_summary", {})
if not isinstance(next_action, dict):
    next_action = {}
holdout = {}
selection_bias_audit = report.get("selection_bias_audit", {})
if not isinstance(selection_bias_audit, dict):
    selection_bias_audit = {}
final_holdout_summary = selection_bias_audit.get("final_holdout_summary", {})
if isinstance(final_holdout_summary, dict):
    strategy_summary = final_holdout_summary.get("strategy_summary", {})
    if isinstance(strategy_summary, dict):
        holdout = strategy_summary
if not holdout:
    fallback_holdout = overview.get("selection_bias_final_holdout_strategy_summary", {})
    if isinstance(fallback_holdout, dict):
        holdout = fallback_holdout
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

trade_coverage: dict[str, dict[str, int]] = {}
route_coverage: list[dict[str, object]] = []
for route in route_results:
    if not isinstance(route, dict):
        continue
    strategy = str(route.get("strategy", "")).strip()
    if not strategy:
        route_key = str(route.get("route_key", "")).strip()
        if ":" in route_key:
            strategy = route_key.split(":", 1)[0].strip()
    if not strategy:
        continue
    metrics = route.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    closed_trades = int(float(metrics.get("closed_trades", 0) or 0))
    bucket = trade_coverage.setdefault(
        strategy,
        {
            "route_count": 0,
            "closed_trades": 0,
            "sub_30_route_count": 0,
            "route_gap_to_30": 0,
            "min_route_closed_trades": closed_trades if closed_trades > 0 else 0,
        },
    )
    bucket["route_count"] += 1
    bucket["closed_trades"] += closed_trades
    if closed_trades < 30:
        bucket["sub_30_route_count"] += 1
        bucket["route_gap_to_30"] += max(0, 30 - closed_trades)
    if bucket["route_count"] == 1 or closed_trades < bucket["min_route_closed_trades"]:
        bucket["min_route_closed_trades"] = closed_trades
    action = route_action_by_key.get(str(route.get("route_key", "")).strip(), {})
    recommendation = str(action.get("recommendation", "")).strip() if isinstance(action, dict) else ""
    if not recommendation:
        recommendation = "monitor" if str(route.get("status", "")).strip() == "pass" else "drop_or_retune"
    route_coverage.append(
        {
            "route_key": str(route.get("route_key", "")).strip(),
            "strategy": strategy,
            "status": str(route.get("status", "")).strip(),
            "closed_trades": closed_trades,
            "gap_to_30": max(0, 30 - closed_trades),
            "gap_to_100": max(0, 100 - closed_trades),
            "recommendation": recommendation,
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

payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "report": str(report_path),
    "portfolio_status": overview.get("portfolio_status", "unknown"),
    "strategy_quality_summary": strategy_quality,
    "portfolio_strategy_priority_summary": strategy_priority,
    "portfolio_next_action_summary": next_action,
    "selection_bias_final_holdout_strategy_summary": holdout,
    "trade_coverage_summary": trade_coverage,
    "route_coverage_summary": route_coverage,
}

if output_format == "json":
    out_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    print(out_path)
    raise SystemExit(0)

lines: list[str] = []
lines.append("# Strategy Quality Report")
lines.append("")
lines.append(f"- generated_at: {payload['generated_at']}")
lines.append(f"- report: {report_path}")
lines.append(f"- portfolio_status: {payload['portfolio_status']}")
lines.append("")
lines.append("## Strategy Quality")
lines.append("| Strategy | Total | Sample Thin | OOS Quality | Recommendation |")
lines.append("|---|---:|---:|---:|---|")
for strategy, item in strategy_quality.items():
    if not isinstance(item, dict):
        continue
    lines.append(
        "| {strategy} | {total} | {sample_thin} | {oos_quality} | {recommendation} |".format(
            strategy=strategy,
            total=int(item.get("total", 0) or 0),
            sample_thin=int(item.get("sample_thin_count", 0) or 0),
            oos_quality=int(item.get("oos_quality_count", 0) or 0),
            recommendation=str(item.get("recommendation", "")),
        )
    )

lines.append("")
lines.append("## Priority Routes")
lines.append("| Strategy | Recommendation | Priority Route Keys |")
lines.append("|---|---|---|")
for strategy, item in strategy_priority.items():
    if not isinstance(item, dict):
        continue
    keys = item.get("priority_route_keys", [])
    lines.append(
        "| {strategy} | {recommendation} | {keys} |".format(
            strategy=strategy,
            recommendation=str(item.get("recommendation", "")),
            keys=", ".join(str(v) for v in keys) if isinstance(keys, list) and keys else "-",
        )
    )

lines.append("")
lines.append("## Route Actions")
lines.append("| Strategy | Selected | Qualified | Recommendation | Accumulate OOS | Drop/Retune |")
lines.append("|---|---:|---:|---|---:|---:|")
for strategy, item in next_action.items():
    if not isinstance(item, dict):
        continue
    accumulate = item.get("accumulate_oos_route_keys", [])
    drop_or_retune = item.get("drop_or_retune_route_keys", [])
    lines.append(
        "| {strategy} | {selected} | {qualified} | {recommendation} | {accumulate} | {drop} |".format(
            strategy=strategy,
            selected=int(item.get("selected_route_count", 0) or 0),
            qualified=int(item.get("qualified_route_count", 0) or 0),
            recommendation=str(item.get("recommendation", "")),
            accumulate=", ".join(str(v) for v in accumulate) if isinstance(accumulate, list) and accumulate else "-",
            drop=", ".join(str(v) for v in drop_or_retune) if isinstance(drop_or_retune, list) and drop_or_retune else "-",
        )
    )

lines.append("")
lines.append("## Trade Coverage")
lines.append("| Strategy | Route Count | Closed Trades | Routes <30 | Min Route Closed Trades | Gap To 30 | Gap To 100 |")
lines.append("|---|---:|---:|---:|---:|---:|---:|")
for strategy, item in trade_coverage.items():
    if not isinstance(item, dict):
        continue
    closed = int(item.get("closed_trades", 0) or 0)
    gap_to_30 = int(item.get("route_gap_to_30", 0) or 0)
    lines.append(
        "| {strategy} | {route_count} | {closed} | {sub_30} | {min_route} | {gap_30} | {gap_100} |".format(
            strategy=strategy,
            route_count=int(item.get("route_count", 0) or 0),
            closed=closed,
            sub_30=int(item.get("sub_30_route_count", 0) or 0),
            min_route=int(item.get("min_route_closed_trades", 0) or 0),
            gap_30=gap_to_30,
            gap_100=max(0, 100 - closed),
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

lines.append("")
lines.append("## Final Holdout Delta")
lines.append(
    "| Strategy | Route Count | Delta PF | Delta Expectancy (bps) | Delta Period PnL | Delta Max DD | Delta Closed Trades |"
)
lines.append("|---|---:|---:|---:|---:|---:|---:|")
for strategy, item in holdout.items():
    if not isinstance(item, dict):
        continue
    lines.append(
        "| {strategy} | {route_count} | {delta_pf:.4f} | {delta_expectancy:.4f} | {delta_pnl:.4f} | {delta_dd:.4f} | {delta_trades:.4f} |".format(
            strategy=strategy,
            route_count=int(item.get("route_count", 0) or 0),
            delta_pf=float(item.get("avg_delta_pf", 0.0) or 0.0),
            delta_expectancy=float(item.get("avg_delta_expectancy_bps", 0.0) or 0.0),
            delta_pnl=float(item.get("avg_delta_period_pnl", 0.0) or 0.0),
            delta_dd=float(item.get("avg_delta_max_dd", 0.0) or 0.0),
            delta_trades=float(item.get("avg_delta_closed_trades", 0.0) or 0.0),
        )
    )

out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(out_path)
PY
