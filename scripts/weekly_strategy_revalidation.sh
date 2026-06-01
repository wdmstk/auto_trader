#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${OUT_DIR:-data/validation/weekly_revalidation}"
mkdir -p "$OUT_DIR"

echo "== weekly strategy revalidation =="

# Fixed operating baseline (Trial B)
export SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT}"
export TIMEFRAMES="${TIMEFRAMES:-15m}"
export STRATEGIES="${STRATEGIES:-range,trend}"
export FOLDS="${FOLDS:-4}"

export RANGE_REQUIRE_REVERSAL_CANDLE="${RANGE_REQUIRE_REVERSAL_CANDLE:-false}"
export RANGE_WICK_RATIO_MIN="${RANGE_WICK_RATIO_MIN:-0.3}"
export RANGE_REENTRY_COOLDOWN_BARS="${RANGE_REENTRY_COOLDOWN_BARS:-2}"
export RANGE_ENABLED_SYMBOLS="${RANGE_ENABLED_SYMBOLS:-SOLUSDT,XRPUSDT,BNBUSDT}"

export TREND_REENTRY_COOLDOWN_BARS="${TREND_REENTRY_COOLDOWN_BARS:-2}"
export TREND_ENABLED_SYMBOLS="${TREND_ENABLED_SYMBOLS:-ETHUSDT,XRPUSDT}"

export FEE_RATE="${FEE_RATE:-0.0002}"
export SLIPPAGE_RATE="${SLIPPAGE_RATE:-0.0002}"
export SPREAD_RATE="${SPREAD_RATE:-0.0001}"
export DELAY_BARS="${DELAY_BARS:-1}"
DRIFT_BASELINE_PATH="${DRIFT_BASELINE_PATH:-data/validation/drift/baseline_stats.json}"
DRIFT_REPORT_PATH="$OUT_DIR/feature_drift_report.json"

SUMMARY_PATH="$OUT_DIR/timeframe_comparison_summary.json"
SUMMARY_PATH="$SUMMARY_PATH" ./scripts/timeframe_comparison.sh

OUT_SUMMARY="$OUT_DIR/cost_grid_summary.jsonl" \
OUT_DIR="$OUT_DIR" \
FEE_RATES="${FEE_RATES:-0.0002,0.0003,0.0004}" \
SLIPPAGE_RATES="${SLIPPAGE_RATES:-0.0002,0.0005}" \
SPREAD_RATES="${SPREAD_RATES:-0.0001,0.0003}" \
DELAY_BARS_LIST="${DELAY_BARS_LIST:-0,1,2}" \
TIMEFRAMES="$TIMEFRAMES" \
STRATEGIES="$STRATEGIES" \
./scripts/backtest_cost_grid.sh

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python -m auto_trader.drift \
  --features-glob "data/features/*_15m_features.parquet" \
  --baseline-path "$DRIFT_BASELINE_PATH" \
  --report-path "$DRIFT_REPORT_PATH" \
  --write-baseline-if-missing true

python - "$OUT_DIR/timeframe_comparison_summary.json" "$OUT_DIR/weekly_revalidation_report.json" "$DRIFT_REPORT_PATH" <<'EOF_PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
drift_path = Path(sys.argv[3])
obj = json.loads(src.read_text())
rows = obj.get("rows", [])
drift = json.loads(drift_path.read_text()) if drift_path.exists() else {}

def mean(strategy: str, key: str) -> float:
    vals = [float(r.get(key, 0.0)) for r in rows if r.get("strategy") == strategy and r.get("timeframe") == "15m"]
    return sum(vals) / len(vals) if vals else 0.0

trend_pf = mean("trend", "pf_mean")
trend_exp = mean("trend", "expectancy_bps_mean")
trend_pnl = mean("trend", "period_pnl_mean")
trend_dd = mean("trend", "max_dd_mean")
range_pf = mean("range", "pf_mean")
range_exp = mean("range", "expectancy_bps_mean")
range_pnl = mean("range", "period_pnl_mean")
range_dd = mean("range", "max_dd_mean")

checks = {
    "trend_pf_ge_1_2": trend_pf >= 1.2,
    "trend_expbps_gt_0": trend_exp > 0.0,
    "trend_period_pnl_gt_0": trend_pnl > 0.0,
    "trend_dd_le_0_08": trend_dd <= 0.08,
    "range_pf_ge_1_2": range_pf >= 1.2,
    "range_expbps_gt_0": range_exp > 0.0,
    "range_period_pnl_gt_0": range_pnl > 0.0,
    "range_dd_le_0_08": range_dd <= 0.08,
}
status = "pass" if all(checks.values()) else "warn"
drift_status = str(drift.get("status", "unknown"))
if drift_status in {"warn", "fail"}:
    status = "warn"
out = {
    "schema_version": "1.1",
    "checked_at": datetime.now(UTC).isoformat(),
    "status": status,
    "metrics": {
        "trend": {"pf": trend_pf, "exp_bps": trend_exp, "period_pnl": trend_pnl, "dd": trend_dd},
        "range": {"pf": range_pf, "exp_bps": range_exp, "period_pnl": range_pnl, "dd": range_dd},
    },
    "checks": checks,
    "drift": {
        "status": drift_status,
        "drift_trade_block": bool(drift.get("drift_trade_block", False)),
        "fail_feature_ratio": float(drift.get("fail_feature_ratio", 0.0) or 0.0),
        "missing_feature_ratio": float(drift.get("missing_feature_ratio", 0.0) or 0.0),
        "report_path": str(drift_path),
    },
}
dst.write_text(json.dumps(out, ensure_ascii=True, indent=2), encoding="utf-8")
print(dst)
EOF_PY

echo "done: $OUT_DIR"
