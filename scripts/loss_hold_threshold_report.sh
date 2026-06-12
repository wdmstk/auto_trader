#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

LOSS_FOLD_REVIEW_JSON="${LOSS_FOLD_REVIEW_JSON:-}"
CANDIDATE_REPORT_PATH="${CANDIDATE_REPORT_PATH:-}"
DATA_ROOT="${DATA_ROOT:-data}"
ANALYSIS_DIR="${ANALYSIS_DIR:-$DATA_ROOT/analysis}"
ROUTES="${ROUTES:-}"
MAX_ROUTES="${MAX_ROUTES:-10}"
THRESHOLDS_HOURS="${THRESHOLDS_HOURS:-2,4,6,8,12,24,36,48}"
OUT_PATH="${OUT_PATH:-data/validation/core_expansion/loss_hold_threshold.md}"
JSON_OUT="${JSON_OUT:-${OUT_PATH%.md}.json}"

mkdir -p "$(dirname "$OUT_PATH")" "$(dirname "$JSON_OUT")"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python - "$LOSS_FOLD_REVIEW_JSON" "$CANDIDATE_REPORT_PATH" "$ANALYSIS_DIR" "$ROUTES" "$MAX_ROUTES" "$THRESHOLDS_HOURS" "$OUT_PATH" "$JSON_OUT" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

loss_fold_review_json = Path(sys.argv[1]) if sys.argv[1] else None
candidate_report_path = Path(sys.argv[2]) if sys.argv[2] else None
analysis_dir = Path(sys.argv[3])
routes_arg = sys.argv[4]
max_routes = int(sys.argv[5])
thresholds = [float(item) for item in sys.argv[6].split(",") if item.strip()]
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
    if loss_fold_review_json and loss_fold_review_json.exists():
        payload = json.loads(loss_fold_review_json.read_text(encoding="utf-8"))
        rows = [row for row in payload.get("routes", []) if isinstance(row, dict)]
        rows = [row for row in rows if row.get("status") == "ok"]
        rows.sort(
            key=lambda row: (
                -int(row.get("negative_fold_count", 0) or 0),
                float(row.get("total_period_pnl", 0.0) or 0.0),
                float(row.get("worst_fold_pnl", 0.0) or 0.0),
            )
        )
        return [str(row.get("route", "")) for row in rows[:max_routes] if row.get("route")]
    if candidate_report_path and candidate_report_path.exists():
        payload = json.loads(candidate_report_path.read_text(encoding="utf-8"))
        rows = [row for row in payload.get("rows", []) if isinstance(row, dict)]
        return [
            f"{row['strategy']}:{row['symbol']}:{row['timeframe']}"
            for row in rows[:max_routes]
        ]
    raise SystemExit("ROUTES or LOSS_FOLD_REVIEW_JSON or CANDIDATE_REPORT_PATH is required")


def _candidate_map() -> dict[str, dict]:
    if not candidate_report_path or not candidate_report_path.exists():
        return {}
    payload = json.loads(candidate_report_path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for row in payload.get("rows", []):
        if isinstance(row, dict):
            out[f"{row['strategy']}:{row['symbol']}:{row['timeframe']}"] = row
    return out


routes = _pick_routes()
candidate_map = _candidate_map()
route_rows: list[dict[str, object]] = []

for route in routes:
    strategy, symbol, timeframe = route.split(":")
    closed_path = analysis_dir / f"walkforward_{symbol}_{timeframe}_{strategy}_closed_trades.parquet"
    if not closed_path.exists():
        route_rows.append({"route": route, "status": "missing_closed_trades"})
        continue
    closed = pd.read_parquet(closed_path).copy()
    if closed.empty:
        route_rows.append({"route": route, "status": "empty_closed_trades"})
        continue
    closed["entry_ts"] = pd.to_datetime(closed["entry_ts"], utc=True)
    closed["exit_ts"] = pd.to_datetime(closed["exit_ts"], utc=True)
    closed["hold_hours"] = (closed["exit_ts"] - closed["entry_ts"]).dt.total_seconds() / 3600.0
    losses = closed[closed["pnl"].astype(float) < 0].copy()
    wins = closed[closed["pnl"].astype(float) > 0].copy()
    candidate = candidate_map.get(route, {})
    threshold_rows: list[dict[str, object]] = []
    total_pnl = _safe_float(closed["pnl"].sum())
    total_loss_pnl_abs = abs(_safe_float(losses["pnl"].sum()))
    for threshold in thresholds:
        impacted = losses[losses["hold_hours"].astype(float) > threshold].copy()
        impacted_loss_abs = abs(_safe_float(impacted["pnl"].sum()))
        threshold_rows.append(
            {
                "threshold_hours": threshold,
                "impacted_trade_count": int(len(impacted)),
                "impacted_loss_abs": impacted_loss_abs,
                "impacted_loss_share": (impacted_loss_abs / total_loss_pnl_abs) if total_loss_pnl_abs > 0 else 0.0,
                "impacted_trade_share": (len(impacted) / len(losses)) if len(losses) > 0 else 0.0,
                "avg_impacted_hold_hours": _safe_float(impacted["hold_hours"].mean()) if not impacted.empty else 0.0,
                "avg_impacted_return_bps": _safe_float(impacted["return_bps"].mean()) if not impacted.empty else 0.0,
                # Diagnostic upper bound only: assumes these losses could be neutralized.
                "upper_bound_pnl_if_neutralized": total_pnl + impacted_loss_abs,
            }
        )
    route_rows.append(
        {
            "route": route,
            "status": "ok",
            "candidate_status": str(candidate.get("candidate_status", "-")),
            "pf_mean": _safe_float(candidate.get("pf_mean", 0.0)),
            "expectancy_bps_mean": _safe_float(candidate.get("expectancy_bps_mean", 0.0)),
            "period_pnl_mean": _safe_float(candidate.get("period_pnl_mean", 0.0)),
            "closed_trades_mean": _safe_float(candidate.get("closed_trades_mean", 0.0)),
            "closed_trade_count": int(len(closed)),
            "loss_trade_count": int(len(losses)),
            "win_trade_count": int(len(wins)),
            "avg_hold_hours": _safe_float(closed["hold_hours"].mean()),
            "loss_avg_hold_hours": _safe_float(losses["hold_hours"].mean()) if not losses.empty else 0.0,
            "win_avg_hold_hours": _safe_float(wins["hold_hours"].mean()) if not wins.empty else 0.0,
            "total_trade_pnl": total_pnl,
            "total_loss_pnl_abs": total_loss_pnl_abs,
            "thresholds": threshold_rows,
        }
    )

payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "analysis_dir": str(analysis_dir),
    "thresholds_hours": thresholds,
    "routes": route_rows,
}
json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines: list[str] = []
lines.append("# Loss Hold Threshold Review")
lines.append("")
lines.append(f"- generated_at: {payload['generated_at']}")
lines.append(f"- analysis_dir: {analysis_dir}")
lines.append(f"- thresholds_hours: {', '.join(str(int(t) if t.is_integer() else t) for t in thresholds)}")
lines.append("- note: `upper_bound_pnl_if_neutralized` は、閾値超の負け trade を損失 0 にできた場合の上限診断であり、再バックテスト結果ではない")
lines.append("")

for route_row in route_rows:
    route = str(route_row.get("route", ""))
    lines.append(f"## {route}")
    lines.append("")
    if route_row.get("status") != "ok":
        lines.append(f"- status: {route_row.get('status')}")
        lines.append("")
        continue
    lines.append(
        "- candidate={status} total_trade_pnl={pnl:.3f} losses={losses} wins={wins} avg_hold={avg_hold:.2f}h loss_avg_hold={loss_avg:.2f}h win_avg_hold={win_avg:.2f}h".format(
            status=str(route_row.get("candidate_status", "-")),
            pnl=_safe_float(route_row.get("total_trade_pnl", 0.0)),
            losses=int(route_row.get("loss_trade_count", 0) or 0),
            wins=int(route_row.get("win_trade_count", 0) or 0),
            avg_hold=_safe_float(route_row.get("avg_hold_hours", 0.0)),
            loss_avg=_safe_float(route_row.get("loss_avg_hold_hours", 0.0)),
            win_avg=_safe_float(route_row.get("win_avg_hold_hours", 0.0)),
        )
    )
    lines.append("")
    lines.append("| Threshold Hrs | Impacted Loss Trades | Impacted Loss Share | Impacted Trade Share | Avg Impacted Hold Hrs | Avg Impacted ReturnBps | Upper Bound PnL If Neutralized |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|")
    for row in route_row["thresholds"]:
        lines.append(
            "| {threshold:.0f} | {count} | {loss_share:.2%} | {trade_share:.2%} | {hold:.2f} | {ret:.2f} | {upper:.3f} |".format(
                threshold=_safe_float(row.get("threshold_hours", 0.0)),
                count=int(row.get("impacted_trade_count", 0) or 0),
                loss_share=_safe_float(row.get("impacted_loss_share", 0.0)),
                trade_share=_safe_float(row.get("impacted_trade_share", 0.0)),
                hold=_safe_float(row.get("avg_impacted_hold_hours", 0.0)),
                ret=_safe_float(row.get("avg_impacted_return_bps", 0.0)),
                upper=_safe_float(row.get("upper_bound_pnl_if_neutralized", 0.0)),
            )
        )
    lines.append("")

out_path.write_text("\n".join(lines), encoding="utf-8")
print(json_out)
print(out_path)
PY
