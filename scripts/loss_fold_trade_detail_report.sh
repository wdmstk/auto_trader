#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

LOSS_FOLD_REVIEW_JSON="${LOSS_FOLD_REVIEW_JSON:-}"
CANDIDATE_REPORT_PATH="${CANDIDATE_REPORT_PATH:-}"
DATA_ROOT="${DATA_ROOT:-data}"
ANALYSIS_DIR="${ANALYSIS_DIR:-$DATA_ROOT/analysis}"
ROUTES="${ROUTES:-}"
MAX_DETAIL_ROUTES="${MAX_DETAIL_ROUTES:-10}"
OUT_PATH="${OUT_PATH:-data/validation/core_expansion/loss_fold_trade_detail.md}"
JSON_OUT="${JSON_OUT:-${OUT_PATH%.md}.json}"

mkdir -p "$(dirname "$OUT_PATH")" "$(dirname "$JSON_OUT")"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python - "$LOSS_FOLD_REVIEW_JSON" "$CANDIDATE_REPORT_PATH" "$DATA_ROOT" "$ANALYSIS_DIR" "$ROUTES" "$MAX_DETAIL_ROUTES" "$OUT_PATH" "$JSON_OUT" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

loss_review_json = Path(sys.argv[1]) if sys.argv[1] else None
candidate_report_path = Path(sys.argv[2]) if sys.argv[2] else None
data_root = Path(sys.argv[3])
analysis_dir = Path(sys.argv[4])
routes_arg = sys.argv[5]
max_detail_routes = int(sys.argv[6])
out_path = Path(sys.argv[7])
json_out = Path(sys.argv[8])


def _safe_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _pick_routes() -> list[str]:
    explicit = [item.strip() for item in routes_arg.split(",") if item.strip()]
    if explicit:
        return explicit
    if loss_review_json and loss_review_json.exists():
        payload = json.loads(loss_review_json.read_text(encoding="utf-8"))
        rows = payload.get("routes", [])
        rows = [row for row in rows if isinstance(row, dict) and row.get("status") == "ok"]
        rows.sort(
            key=lambda row: (
                -int(row.get("negative_fold_count", 0) or 0),
                float(row.get("total_period_pnl", 0.0) or 0.0),
                float(row.get("worst_fold_pnl", 0.0) or 0.0),
            )
        )
        return [str(row.get("route", "")) for row in rows[:max_detail_routes] if row.get("route")]
    if candidate_report_path and candidate_report_path.exists():
        payload = json.loads(candidate_report_path.read_text(encoding="utf-8"))
        rows = [row for row in payload.get("rows", []) if isinstance(row, dict)]
        return [
            f"{row['strategy']}:{row['symbol']}:{row['timeframe']}"
            for row in rows[:max_detail_routes]
        ]
    raise SystemExit("ROUTES or LOSS_FOLD_REVIEW_JSON or CANDIDATE_REPORT_PATH is required")


def _load_candidate_map() -> dict[str, dict]:
    if not candidate_report_path or not candidate_report_path.exists():
        return {}
    payload = json.loads(candidate_report_path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        out[f"{row['strategy']}:{row['symbol']}:{row['timeframe']}"] = row
    return out


def _series_quantile(frame: pd.DataFrame, col: str, q: float) -> float:
    if frame.empty or col not in frame.columns:
        return 0.0
    return _safe_float(frame[col].astype(float).quantile(q))


routes = _pick_routes()
candidate_map = _load_candidate_map()
detail_rows: list[dict[str, object]] = []

for route in routes:
    try:
        strategy, symbol, timeframe = route.split(":")
    except ValueError as exc:
        raise SystemExit(f"invalid route format: {route}") from exc

    summary_path = analysis_dir / f"walkforward_{symbol}_{timeframe}_{strategy}_summary.parquet"
    closed_path = analysis_dir / f"walkforward_{symbol}_{timeframe}_{strategy}_closed_trades.parquet"
    portfolio_path = analysis_dir / f"walkforward_{symbol}_{timeframe}_{strategy}_portfolio.parquet"
    if not summary_path.exists():
        detail_rows.append({"route": route, "status": "missing_summary"})
        continue

    summary = pd.read_parquet(summary_path).copy()
    if summary.empty:
        detail_rows.append({"route": route, "status": "empty_summary"})
        continue

    closed = pd.read_parquet(closed_path).copy() if closed_path.exists() else pd.DataFrame()
    portfolio = pd.read_parquet(portfolio_path).copy() if portfolio_path.exists() else pd.DataFrame()
    if not closed.empty:
        closed["entry_ts"] = pd.to_datetime(closed["entry_ts"], utc=True)
        closed["exit_ts"] = pd.to_datetime(closed["exit_ts"], utc=True)
        closed["hold_hours"] = (
            (closed["exit_ts"] - closed["entry_ts"]).dt.total_seconds() / 3600.0
        )
    if not portfolio.empty:
        portfolio["timestamp"] = pd.to_datetime(portfolio["timestamp"], utc=True)

    negative = summary[summary["period_pnl"].astype(float) < 0].copy().sort_values("period_pnl")
    candidate = candidate_map.get(route, {})
    route_detail = {
        "route": route,
        "candidate_status": str(candidate.get("candidate_status", "-")),
        "pf_mean": _safe_float(candidate.get("pf_mean", 0.0)),
        "expectancy_bps_mean": _safe_float(candidate.get("expectancy_bps_mean", 0.0)),
        "period_pnl_mean": _safe_float(candidate.get("period_pnl_mean", 0.0)),
        "closed_trades_mean": _safe_float(candidate.get("closed_trades_mean", 0.0)),
        "negative_folds": [],
    }

    for _, fold_row in negative.iterrows():
        fold = int(_safe_float(fold_row.get("fold", 0)))
        trades = closed[pd.to_numeric(closed["fold"]) == fold].copy() if not closed.empty and "fold" in closed.columns else pd.DataFrame()
        pfold = portfolio[pd.to_numeric(portfolio["fold"]) == fold].copy() if not portfolio.empty and "fold" in portfolio.columns else pd.DataFrame()
        fold_start = ""
        fold_end = ""
        trough_ts = ""
        if not pfold.empty:
            pfold = pfold.sort_values("timestamp")
            fold_start = pfold["timestamp"].iloc[0].isoformat()
            fold_end = pfold["timestamp"].iloc[-1].isoformat()
            if "drawdown" in pfold.columns:
                trough_ts = pfold.sort_values("drawdown", ascending=False)["timestamp"].iloc[0].isoformat()
        worst_trades: list[dict[str, object]] = []
        if not trades.empty:
            for _, trade in trades.sort_values("pnl").head(3).iterrows():
                worst_trades.append(
                    {
                        "entry_ts": trade["entry_ts"].isoformat(),
                        "exit_ts": trade["exit_ts"].isoformat(),
                        "pnl": _safe_float(trade.get("pnl", 0.0)),
                        "return_bps": _safe_float(trade.get("return_bps", 0.0)),
                        "hold_hours": _safe_float(trade.get("hold_hours", 0.0)),
                    }
                )
        route_detail["negative_folds"].append(
            {
                "fold": fold,
                "period_start": fold_start,
                "period_end": fold_end,
                "max_drawdown_ts": trough_ts,
                "entries": _safe_float(fold_row.get("entries", 0.0)),
                "closed_trades": _safe_float(fold_row.get("closed_trades", 0.0)),
                "pf": _safe_float(fold_row.get("pf", 0.0)),
                "expectancy_bps": _safe_float(fold_row.get("expectancy_bps", 0.0)),
                "period_pnl": _safe_float(fold_row.get("period_pnl", 0.0)),
                "gross_pnl_est": _safe_float(fold_row.get("gross_pnl_est", 0.0)),
                "total_cost_est": _safe_float(fold_row.get("total_cost_est", 0.0)),
                "max_dd": _safe_float(fold_row.get("max_dd", 0.0)),
                "trade_count": int(len(trades)),
                "loss_trade_count": int((trades["pnl"].astype(float) <= 0).sum()) if not trades.empty else 0,
                "win_trade_count": int((trades["pnl"].astype(float) > 0).sum()) if not trades.empty else 0,
                "avg_hold_hours": _safe_float(trades["hold_hours"].mean()) if not trades.empty else 0.0,
                "median_hold_hours": _safe_float(trades["hold_hours"].median()) if not trades.empty else 0.0,
                "avg_return_bps": _safe_float(trades["return_bps"].mean()) if not trades.empty else 0.0,
                "q10_return_bps": _series_quantile(trades, "return_bps", 0.10),
                "q50_return_bps": _series_quantile(trades, "return_bps", 0.50),
                "q90_return_bps": _series_quantile(trades, "return_bps", 0.90),
                "worst_trade_pnl": _safe_float(trades["pnl"].min()) if not trades.empty else 0.0,
                "worst_trade_return_bps": _safe_float(trades["return_bps"].min()) if not trades.empty else 0.0,
                "worst_trades": worst_trades,
            }
        )
    detail_rows.append(route_detail)

payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "data_root": str(data_root),
    "analysis_dir": str(analysis_dir),
    "routes": detail_rows,
}
json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines: list[str] = []
lines.append("# Loss Fold Trade Detail")
lines.append("")
lines.append(f"- generated_at: {payload['generated_at']}")
lines.append(f"- data_root: {data_root}")
lines.append(f"- analysis_dir: {analysis_dir}")
lines.append(f"- detailed_routes: {len(detail_rows)}")
lines.append("")

for route_row in detail_rows:
    route = str(route_row.get("route", ""))
    lines.append(f"## {route}")
    lines.append("")
    if route_row.get("status") in {"missing_summary", "empty_summary"}:
        lines.append(f"- status: {route_row['status']}")
        lines.append("")
        continue
    lines.append(
        "- candidate={status} pf_mean={pf:.3f} expbps_mean={exp:.2f} pnl_mean={pnl:.3f} trades_mean={trades:.2f}".format(
            status=str(route_row.get("candidate_status", "-")),
            pf=_safe_float(route_row.get("pf_mean", 0.0)),
            exp=_safe_float(route_row.get("expectancy_bps_mean", 0.0)),
            pnl=_safe_float(route_row.get("period_pnl_mean", 0.0)),
            trades=_safe_float(route_row.get("closed_trades_mean", 0.0)),
        )
    )
    lines.append("")
    lines.append("| Fold | Start | End | DD Trough | PF | EXPbps | PeriodPnL | GrossPnL | Cost | Closed | Avg Hold Hrs | q10/q50/q90 ReturnBps |")
    lines.append("|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for fold in route_row["negative_folds"]:
        lines.append(
            "| {fold_id} | {start} | {end} | {trough} | {pf:.3f} | {exp:.2f} | {pnl:.3f} | {gross:.3f} | {cost:.3f} | {closed} | {hold:.2f} | {q10:.2f} / {q50:.2f} / {q90:.2f} |".format(
                fold_id=int(fold.get("fold", 0) or 0),
                start=str(fold.get("period_start", "")) or "-",
                end=str(fold.get("period_end", "")) or "-",
                trough=str(fold.get("max_drawdown_ts", "")) or "-",
                pf=_safe_float(fold.get("pf", 0.0)),
                exp=_safe_float(fold.get("expectancy_bps", 0.0)),
                pnl=_safe_float(fold.get("period_pnl", 0.0)),
                gross=_safe_float(fold.get("gross_pnl_est", 0.0)),
                cost=_safe_float(fold.get("total_cost_est", 0.0)),
                closed=int(fold.get("trade_count", 0) or 0),
                hold=_safe_float(fold.get("avg_hold_hours", 0.0)),
                q10=_safe_float(fold.get("q10_return_bps", 0.0)),
                q50=_safe_float(fold.get("q50_return_bps", 0.0)),
                q90=_safe_float(fold.get("q90_return_bps", 0.0)),
            )
        )
    lines.append("")
    for fold in route_row["negative_folds"]:
        lines.append(f"### Fold {int(fold.get('fold', 0) or 0)}")
        lines.append("")
        lines.append(
            "- trades={trades} loss_trades={losses} win_trades={wins} avg_hold={avg_hold:.2f}h median_hold={median_hold:.2f}h avg_return={avg_return:.2f}bps worst_trade={worst_trade:.3f} worst_return={worst_return:.2f}bps".format(
                trades=int(fold.get("trade_count", 0) or 0),
                losses=int(fold.get("loss_trade_count", 0) or 0),
                wins=int(fold.get("win_trade_count", 0) or 0),
                avg_hold=_safe_float(fold.get("avg_hold_hours", 0.0)),
                median_hold=_safe_float(fold.get("median_hold_hours", 0.0)),
                avg_return=_safe_float(fold.get("avg_return_bps", 0.0)),
                worst_trade=_safe_float(fold.get("worst_trade_pnl", 0.0)),
                worst_return=_safe_float(fold.get("worst_trade_return_bps", 0.0)),
            )
        )
        lines.append("")
        lines.append("| Worst Trade Entry | Worst Trade Exit | PnL | ReturnBps | Hold Hrs |")
        lines.append("|---|---|---:|---:|---:|")
        worst_trades = fold.get("worst_trades", [])
        if worst_trades:
            for trade in worst_trades:
                lines.append(
                    "| {entry} | {exit} | {pnl:.3f} | {ret:.2f} | {hold:.2f} |".format(
                        entry=str(trade.get("entry_ts", "")),
                        exit=str(trade.get("exit_ts", "")),
                        pnl=_safe_float(trade.get("pnl", 0.0)),
                        ret=_safe_float(trade.get("return_bps", 0.0)),
                        hold=_safe_float(trade.get("hold_hours", 0.0)),
                    )
                )
        else:
            lines.append("| - | - | 0.000 | 0.00 | 0.00 |")
        lines.append("")

out_path.write_text("\n".join(lines), encoding="utf-8")
print(json_out)
print(out_path)
PY
