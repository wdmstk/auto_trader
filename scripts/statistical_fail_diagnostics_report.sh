#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
QUALIFICATION_REPORT_PATH="${QUALIFICATION_REPORT_PATH:-data/validation/statistical_qualification/qualification_report.json}"
ANALYSIS_DIR="${ANALYSIS_DIR:-data/validation/weekly_autotune/weekly_revalidation/manifest_route_run_data/analysis}"
OUTPUT_JSON="${OUTPUT_JSON:-}"
OUTPUT_MD="${OUTPUT_MD:-}"

"$PYTHON_BIN" - "$QUALIFICATION_REPORT_PATH" "$ANALYSIS_DIR" "$OUTPUT_JSON" "$OUTPUT_MD" <<'PY'
from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


def route_stamp(symbol: str, timeframe: str, strategy: str) -> str:
    return f"{symbol}_{timeframe}_{strategy}"


def fail_classification(reasons: list[str], metrics: dict[str, float | int]) -> tuple[str, list[str], list[str]]:
    quick_wins: list[str] = []
    structural: list[str] = []
    closed_trades = int(metrics.get("closed_trades", 0) or 0)

    if "min_route_trades" in reasons:
        structural.append("OOS trade count is below threshold; more samples are required.")
    if "pf_ci_lower" in reasons or "expectancy_bps_ci_lower" in reasons or "mc_loss_probability" in reasons:
        if closed_trades < 30:
            structural.append("Confidence interval failure is mainly sample-size driven.")
        else:
            structural.append("Bootstrap confidence is weak even with enough trades.")
    if any(reason in reasons for reason in ("pf", "expectancy_bps", "period_pnl")):
        structural.append("Final OOS fold quality is below the live gate; route logic must improve.")

    if "period_pnl" not in reasons and "pf" not in reasons and "expectancy_bps" not in reasons:
        quick_wins.append("Keep the route on watch and accumulate more OOS trades before retuning.")
        quick_wins.append("If retuning, prioritize slightly higher trade frequency without worsening DD.")
    else:
        quick_wins.append("Run targeted tuning against the final OOS failure fold before promoting again.")
        quick_wins.append("Compare current route against neighboring hold/exit/cooldown settings and demote if the loss fold persists.")

    if not structural:
        structural.append("No structural issue classified; inspect route manually.")
    return ("sample_thin" if closed_trades < 30 and "period_pnl" not in reasons and "pf" not in reasons and "expectancy_bps" not in reasons else "oos_quality"), quick_wins, structural


def summarize_fold(closed: pd.DataFrame) -> list[dict[str, object]]:
    if closed.empty:
        return []
    frame = closed.copy()
    for col in ("pnl", "return_bps", "fold"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    grouped = frame.groupby("fold", dropna=False)
    rows: list[dict[str, object]] = []
    for fold, part in grouped:
        pnl = pd.to_numeric(part["pnl"], errors="coerce").fillna(0.0)
        pos = float(pnl[pnl > 0].sum())
        neg = float(abs(pnl[pnl < 0].sum()))
        pf = pos / neg if neg > 0 else (math.inf if pos > 0 else 0.0)
        rows.append(
            {
                "fold": int(fold),
                "closed_trades": int(len(part)),
                "period_pnl": float(pnl.sum()),
                "expectancy_bps": float(pd.to_numeric(part["return_bps"], errors="coerce").mean()),
                "win_rate": float((pnl > 0).mean()) if len(part) else 0.0,
                "pf": float(pf),
            }
        )
    return rows


def worst_trades(closed: pd.DataFrame, limit: int = 5) -> list[dict[str, object]]:
    cols = [col for col in ("entry_ts", "exit_ts", "pnl", "return_bps", "entry_notional", "fold") if col in closed.columns]
    if not cols or closed.empty:
        return []
    frame = closed[cols].copy()
    if "pnl" in frame.columns:
        frame["pnl"] = pd.to_numeric(frame["pnl"], errors="coerce")
    if "return_bps" in frame.columns:
        frame["return_bps"] = pd.to_numeric(frame["return_bps"], errors="coerce")
    out = []
    for row in frame.sort_values("pnl").head(limit).to_dict(orient="records"):
        for key in ("entry_ts", "exit_ts"):
            value = row.get(key)
            if value is not None and hasattr(value, "isoformat"):
                row[key] = value.isoformat()
        out.append(row)
    return out


qualification_path = Path(sys.argv[1])
analysis_dir = Path(sys.argv[2])
output_json_arg = sys.argv[3].strip()
output_md_arg = sys.argv[4].strip()

default_output_dir = (
    analysis_dir.parents[1]
    if len(analysis_dir.parents) >= 2
    else qualification_path.parent
)
output_json = Path(output_json_arg) if output_json_arg else default_output_dir / "statistical_fail_diagnostics.json"
output_md = Path(output_md_arg) if output_md_arg else default_output_dir / "statistical_fail_diagnostics.md"

qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
routes = [route for route in qualification.get("routes", []) if isinstance(route, dict) and route.get("status") == "fail"]

diagnostics: list[dict[str, object]] = []
for route in routes:
    symbol = str(route.get("symbol", ""))
    timeframe = str(route.get("timeframe", ""))
    strategy = str(route.get("strategy", ""))
    stamp = route_stamp(symbol, timeframe, strategy)
    closed_path = analysis_dir / f"walkforward_{stamp}_closed_trades.parquet"
    closed = pd.read_parquet(closed_path) if closed_path.exists() else pd.DataFrame()
    fold_rows = summarize_fold(closed)
    final_fold = max((int(row["fold"]) for row in fold_rows), default=-1)
    final_fold_rows = closed[pd.to_numeric(closed.get("fold"), errors="coerce") == final_fold].copy() if not closed.empty and "fold" in closed.columns else pd.DataFrame()
    category, quick_wins, structural = fail_classification(list(route.get("reasons", [])), dict(route.get("metrics", {})))
    diagnostics.append(
        {
            "route_key": str(route.get("route_key", "")),
            "category": category,
            "reasons": list(route.get("reasons", [])),
            "metrics": dict(route.get("metrics", {})),
            "oos": dict(route.get("oos", {})),
            "fold_breakdown": fold_rows,
            "worst_trades_final_fold": worst_trades(final_fold_rows),
            "quick_wins": quick_wins,
            "structural_actions": structural,
        }
    )

payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "qualification_report_path": str(qualification_path),
    "analysis_dir": str(analysis_dir),
    "route_count": len(diagnostics),
    "routes": diagnostics,
}
output_json.parent.mkdir(parents=True, exist_ok=True)
output_json.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines = [
    "# Statistical Fail Diagnostics",
    "",
    f"- generated_at: {payload['generated_at']}",
    f"- qualification_report_path: {qualification_path}",
    f"- analysis_dir: {analysis_dir}",
    f"- route_count: {len(diagnostics)}",
    "",
]
for route in diagnostics:
    metrics = route["metrics"]
    oos = route["oos"]
    lines.extend(
        [
            f"## {route['route_key']}",
            "",
            f"- category: {route['category']}",
            f"- reasons: {', '.join(route['reasons'])}",
            f"- OOS days: {oos.get('days', '-')}",
            f"- OOS ratio: {oos.get('ratio', '-')}",
            f"- closed_trades: {metrics.get('closed_trades', '-')}",
            f"- pf: {metrics.get('pf', '-')}",
            f"- expectancy_bps: {metrics.get('expectancy_bps', '-')}",
            f"- period_pnl: {metrics.get('period_pnl', '-')}",
            f"- pf_ci_lower: {metrics.get('pf_ci_lower', '-')}",
            f"- expectancy_bps_ci_lower: {metrics.get('expectancy_bps_ci_lower', '-')}",
            f"- mc_loss_probability: {metrics.get('mc_loss_probability', '-')}",
            "",
            "### Fold Breakdown",
            "",
            "| Fold | Trades | PnL | EXPbps | WinRate | PF |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for fold in route["fold_breakdown"]:
        lines.append(
            "| {fold} | {closed_trades} | {period_pnl:.6f} | {expectancy_bps:.2f} | {win_rate:.2%} | {pf:.3f} |".format(
                **fold
            )
        )
    lines.extend(["", "### Quick Wins", ""])
    for item in route["quick_wins"]:
        lines.append(f"- {item}")
    lines.extend(["", "### Structural Actions", ""])
    for item in route["structural_actions"]:
        lines.append(f"- {item}")
    if route["worst_trades_final_fold"]:
        lines.extend(["", "### Worst Trades In Final Fold", "", "| Entry | Exit | PnL | Return bps | Notional | Fold |", "|---|---|---:|---:|---:|---:|"])
        for row in route["worst_trades_final_fold"]:
            lines.append(
                f"| {row.get('entry_ts', '-')} | {row.get('exit_ts', '-')} | {float(row.get('pnl', 0.0)):.6f} | {float(row.get('return_bps', 0.0)):.2f} | {float(row.get('entry_notional', 0.0)):.6f} | {int(row.get('fold', 0))} |"
            )
    lines.extend(["", ""])

output_md.write_text("\n".join(lines), encoding="utf-8")
print(output_json)
print(output_md)
PY
