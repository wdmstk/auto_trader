#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

CANDIDATE_REPORT_PATH="${CANDIDATE_REPORT_PATH:-}"
DATA_ROOT="${DATA_ROOT:-data}"
ANALYSIS_DIR="${ANALYSIS_DIR:-$DATA_ROOT/analysis}"
ROUTES="${ROUTES:-}"
OUT_PATH="${OUT_PATH:-data/validation/core_expansion/loss_fold_review.md}"
JSON_OUT="${JSON_OUT:-${OUT_PATH%.md}.json}"

mkdir -p "$(dirname "$OUT_PATH")" "$(dirname "$JSON_OUT")"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python - "$CANDIDATE_REPORT_PATH" "$DATA_ROOT" "$ANALYSIS_DIR" "$ROUTES" "$OUT_PATH" "$JSON_OUT" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

candidate_report_path = Path(sys.argv[1]) if sys.argv[1] else None
data_root = Path(sys.argv[2])
analysis_dir = Path(sys.argv[3])
routes_arg = sys.argv[4]
out_path = Path(sys.argv[5])
json_out = Path(sys.argv[6])


def _parse_routes() -> list[str]:
    explicit = [item.strip() for item in routes_arg.split(",") if item.strip()]
    if explicit:
        return explicit
    if candidate_report_path and candidate_report_path.exists():
        payload = json.loads(candidate_report_path.read_text(encoding="utf-8"))
        rows = payload.get("rows", [])
        return [
            f"{row['strategy']}:{row['symbol']}:{row['timeframe']}"
            for row in rows
            if isinstance(row, dict)
        ]
    raise SystemExit("ROUTES or CANDIDATE_REPORT_PATH is required")


def _load_candidate_map() -> dict[str, dict]:
    if not candidate_report_path or not candidate_report_path.exists():
        return {}
    payload = json.loads(candidate_report_path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        route = f"{row['strategy']}:{row['symbol']}:{row['timeframe']}"
        out[route] = row
    return out


def _safe_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _loss_kind(period_pnl: float, gross_pnl: float) -> str:
    if period_pnl >= 0:
        return "non_loss"
    if gross_pnl <= 0:
        return "gross_loss"
    return "cost_drag"


routes = _parse_routes()
candidate_map = _load_candidate_map()
route_results: list[dict[str, object]] = []
negative_fold_rows: list[dict[str, object]] = []

for route in routes:
    try:
        strategy, symbol, timeframe = route.split(":")
    except ValueError as exc:
        raise SystemExit(f"invalid route format: {route}") from exc

    summary_path = analysis_dir / f"walkforward_{symbol}_{timeframe}_{strategy}_summary.parquet"
    closed_path = analysis_dir / f"walkforward_{symbol}_{timeframe}_{strategy}_closed_trades.parquet"
    if not summary_path.exists():
        route_results.append({"route": route, "status": "missing_summary"})
        continue

    summary = pd.read_parquet(summary_path).copy()
    if summary.empty:
        route_results.append({"route": route, "status": "empty_summary"})
        continue

    closed = pd.read_parquet(closed_path).copy() if closed_path.exists() else pd.DataFrame()
    if not closed.empty:
        closed["entry_ts"] = pd.to_datetime(closed["entry_ts"], utc=True)
        closed["exit_ts"] = pd.to_datetime(closed["exit_ts"], utc=True)
        closed["hold_hours"] = (
            (closed["exit_ts"] - closed["entry_ts"]).dt.total_seconds() / 3600.0
        )

    negative = summary[summary["period_pnl"].astype(float) < 0].copy()
    negative = negative.sort_values("period_pnl", ascending=True)
    candidate = candidate_map.get(route, {})

    route_result = {
        "route": route,
        "status": "ok",
        "candidate_status": str(candidate.get("candidate_status", "-")),
        "candidate_score": _safe_float(candidate.get("candidate_score", 0.0)),
        "pf_mean": _safe_float(candidate.get("pf_mean", 0.0)),
        "expectancy_bps_mean": _safe_float(candidate.get("expectancy_bps_mean", 0.0)),
        "period_pnl_mean": _safe_float(candidate.get("period_pnl_mean", 0.0)),
        "closed_trades_mean": _safe_float(candidate.get("closed_trades_mean", 0.0)),
        "negative_fold_count": int(len(negative)),
        "fold_count": int(len(summary)),
        "total_period_pnl": _safe_float(summary["period_pnl"].sum()),
        "total_gross_pnl_est": _safe_float(summary["gross_pnl_est"].sum()),
        "total_cost_est": _safe_float(summary["total_cost_est"].sum()),
        "worst_fold": int(negative.iloc[0]["fold"]) if not negative.empty else None,
        "worst_fold_pnl": _safe_float(negative.iloc[0]["period_pnl"]) if not negative.empty else 0.0,
    }
    route_results.append(route_result)

    for _, row in negative.iterrows():
        fold = int(_safe_float(row.get("fold", 0)))
        trades = pd.DataFrame()
        if not closed.empty and "fold" in closed.columns:
            trades = closed[pd.to_numeric(closed["fold"]) == fold].copy()
        wins = trades[trades["pnl"].astype(float) > 0].copy() if not trades.empty else pd.DataFrame()
        losses = trades[trades["pnl"].astype(float) <= 0].copy() if not trades.empty else pd.DataFrame()
        negative_fold_rows.append(
            {
                "route": route,
                "strategy": strategy,
                "symbol": symbol,
                "timeframe": timeframe,
                "candidate_status": str(candidate.get("candidate_status", "-")),
                "fold": fold,
                "loss_kind": _loss_kind(
                    _safe_float(row.get("period_pnl", 0.0)),
                    _safe_float(row.get("gross_pnl_est", 0.0)),
                ),
                "entries": _safe_float(row.get("entries", 0.0)),
                "closed_trades": _safe_float(row.get("closed_trades", 0.0)),
                "pf": _safe_float(row.get("pf", 0.0)),
                "expectancy_bps": _safe_float(row.get("expectancy_bps", 0.0)),
                "period_pnl": _safe_float(row.get("period_pnl", 0.0)),
                "gross_pnl_est": _safe_float(row.get("gross_pnl_est", 0.0)),
                "total_cost_est": _safe_float(row.get("total_cost_est", 0.0)),
                "max_dd": _safe_float(row.get("max_dd", 0.0)),
                "win_rate": _safe_float(row.get("win_rate", 0.0)),
                "avg_trade_pnl": _safe_float(trades["pnl"].mean()) if not trades.empty else 0.0,
                "median_trade_pnl": _safe_float(trades["pnl"].median()) if not trades.empty else 0.0,
                "worst_trade_pnl": _safe_float(trades["pnl"].min()) if not trades.empty else 0.0,
                "avg_return_bps": _safe_float(trades["return_bps"].mean()) if "return_bps" in trades.columns and not trades.empty else 0.0,
                "worst_return_bps": _safe_float(trades["return_bps"].min()) if "return_bps" in trades.columns and not trades.empty else 0.0,
                "avg_hold_hours": _safe_float(trades["hold_hours"].mean()) if "hold_hours" in trades.columns and not trades.empty else 0.0,
                "loss_trade_count": int(len(losses)),
                "win_trade_count": int(len(wins)),
            }
        )

route_results.sort(
    key=lambda row: (
        -int(row.get("negative_fold_count", 0) or 0),
        float(row.get("total_period_pnl", 0.0) or 0.0),
        float(row.get("worst_fold_pnl", 0.0) or 0.0),
        str(row.get("route", "")),
    )
)
negative_fold_rows.sort(
    key=lambda row: (
        float(row.get("period_pnl", 0.0) or 0.0),
        float(row.get("expectancy_bps", 0.0) or 0.0),
        str(row.get("route", "")),
        int(row.get("fold", 0) or 0),
    )
)

payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "data_root": str(data_root),
    "analysis_dir": str(analysis_dir),
    "candidate_report_path": str(candidate_report_path) if candidate_report_path else "",
    "routes": route_results,
    "negative_folds": negative_fold_rows,
}
json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines: list[str] = []
lines.append("# Loss Fold Review")
lines.append("")
lines.append(f"- generated_at: {payload['generated_at']}")
lines.append(f"- data_root: {data_root}")
lines.append(f"- analysis_dir: {analysis_dir}")
if candidate_report_path:
    lines.append(f"- candidate_report: {candidate_report_path}")
lines.append(f"- reviewed_routes: {len(route_results)}")
lines.append(f"- negative_fold_rows: {len(negative_fold_rows)}")
lines.append("")
lines.append("| Route | Candidate | Neg Folds | TotalPnL | Worst Fold | WorstPnL | PF Mean | EXPbps Mean | Trades Mean |")
lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
for row in route_results:
    lines.append(
        "| {route} | {status} | {neg} | {pnl:.3f} | {worst_fold} | {worst_pnl:.3f} | {pf:.3f} | {exp:.2f} | {trades:.2f} |".format(
            route=str(row.get("route", "")),
            status=str(row.get("candidate_status", row.get("status", "-"))),
            neg=int(row.get("negative_fold_count", 0) or 0),
            pnl=_safe_float(row.get("total_period_pnl", 0.0)),
            worst_fold="-" if row.get("worst_fold") is None else int(row.get("worst_fold", 0)),
            worst_pnl=_safe_float(row.get("worst_fold_pnl", 0.0)),
            pf=_safe_float(row.get("pf_mean", 0.0)),
            exp=_safe_float(row.get("expectancy_bps_mean", 0.0)),
            trades=_safe_float(row.get("closed_trades_mean", 0.0)),
        )
    )
lines.append("")
lines.append("## Worst Negative Folds")
lines.append("")
lines.append("| Route | Fold | Kind | Candidate | Entries | Closed | PF | EXPbps | PeriodPnL | GrossPnL | Cost | DD | Avg TradePnL | Worst TradePnL | Avg Hold Hrs |")
lines.append("|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
for row in negative_fold_rows[:40]:
    lines.append(
        "| {route} | {fold} | {kind} | {status} | {entries:.0f} | {closed:.0f} | {pf:.3f} | {exp:.2f} | {pnl:.3f} | {gross:.3f} | {cost:.3f} | {dd:.5f} | {avg_trade:.3f} | {worst_trade:.3f} | {hold:.2f} |".format(
            route=str(row.get("route", "")),
            fold=int(row.get("fold", 0) or 0),
            kind=str(row.get("loss_kind", "")),
            status=str(row.get("candidate_status", "-")),
            entries=_safe_float(row.get("entries", 0.0)),
            closed=_safe_float(row.get("closed_trades", 0.0)),
            pf=_safe_float(row.get("pf", 0.0)),
            exp=_safe_float(row.get("expectancy_bps", 0.0)),
            pnl=_safe_float(row.get("period_pnl", 0.0)),
            gross=_safe_float(row.get("gross_pnl_est", 0.0)),
            cost=_safe_float(row.get("total_cost_est", 0.0)),
            dd=_safe_float(row.get("max_dd", 0.0)),
            avg_trade=_safe_float(row.get("avg_trade_pnl", 0.0)),
            worst_trade=_safe_float(row.get("worst_trade_pnl", 0.0)),
            hold=_safe_float(row.get("avg_hold_hours", 0.0)),
        )
    )
lines.append("")

for route_row in route_results:
    route = str(route_row.get("route", ""))
    folds = [row for row in negative_fold_rows if str(row.get("route", "")) == route]
    if not folds:
        continue
    lines.append(f"## {route}")
    lines.append("")
    lines.append(
        "- candidate={status} neg_folds={neg}/{total} total_pnl={pnl:.3f} total_cost={cost:.3f}".format(
            status=str(route_row.get("candidate_status", route_row.get("status", "-"))),
            neg=int(route_row.get("negative_fold_count", 0) or 0),
            total=int(route_row.get("fold_count", 0) or 0),
            pnl=_safe_float(route_row.get("total_period_pnl", 0.0)),
            cost=_safe_float(route_row.get("total_cost_est", 0.0)),
        )
    )
    lines.append("")
    lines.append("| Fold | Kind | Entries | Closed | PF | EXPbps | PeriodPnL | GrossPnL | Cost | DD | Loss Trades | Win Trades | Avg TradePnL | Worst TradePnL | Avg Hold Hrs |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in folds:
        lines.append(
            "| {fold} | {kind} | {entries:.0f} | {closed:.0f} | {pf:.3f} | {exp:.2f} | {pnl:.3f} | {gross:.3f} | {cost:.3f} | {dd:.5f} | {loss_trades} | {win_trades} | {avg_trade:.3f} | {worst_trade:.3f} | {hold:.2f} |".format(
                fold=int(row.get("fold", 0) or 0),
                kind=str(row.get("loss_kind", "")),
                entries=_safe_float(row.get("entries", 0.0)),
                closed=_safe_float(row.get("closed_trades", 0.0)),
                pf=_safe_float(row.get("pf", 0.0)),
                exp=_safe_float(row.get("expectancy_bps", 0.0)),
                pnl=_safe_float(row.get("period_pnl", 0.0)),
                gross=_safe_float(row.get("gross_pnl_est", 0.0)),
                cost=_safe_float(row.get("total_cost_est", 0.0)),
                dd=_safe_float(row.get("max_dd", 0.0)),
                loss_trades=int(row.get("loss_trade_count", 0) or 0),
                win_trades=int(row.get("win_trade_count", 0) or 0),
                avg_trade=_safe_float(row.get("avg_trade_pnl", 0.0)),
                worst_trade=_safe_float(row.get("worst_trade_pnl", 0.0)),
                hold=_safe_float(row.get("avg_hold_hours", 0.0)),
            )
        )
    lines.append("")

out_path.write_text("\n".join(lines), encoding="utf-8")
print(json_out)
print(out_path)
PY
