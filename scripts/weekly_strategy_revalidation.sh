#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${OUT_DIR:-data/validation/weekly_revalidation}"
mkdir -p "$OUT_DIR"

echo "== weekly strategy revalidation =="

# Fixed operating baseline (Trial B)
export SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT,ADAUSDT}"
export TIMEFRAMES="${TIMEFRAMES:-15m}"
export STRATEGIES="${STRATEGIES:-range,trend}"
export FOLDS="${FOLDS:-4}"

export RANGE_REQUIRE_REVERSAL_CANDLE="${RANGE_REQUIRE_REVERSAL_CANDLE:-false}"
export RANGE_WICK_RATIO_MIN="${RANGE_WICK_RATIO_MIN:-0.3}"
export RANGE_REENTRY_COOLDOWN_BARS="${RANGE_REENTRY_COOLDOWN_BARS:-2}"
export RANGE_ENABLED_SYMBOLS="${RANGE_ENABLED_SYMBOLS:-SOLUSDT,XRPUSDT,BNBUSDT}"

export TREND_REENTRY_COOLDOWN_BARS="${TREND_REENTRY_COOLDOWN_BARS:-2}"
export TREND_ENABLED_SYMBOLS="${TREND_ENABLED_SYMBOLS:-ETHUSDT,XRPUSDT,ADAUSDT}"

export FEE_RATE="${FEE_RATE:-0.0002}"
export SLIPPAGE_RATE="${SLIPPAGE_RATE:-0.0002}"
export SPREAD_RATE="${SPREAD_RATE:-0.0001}"
export DELAY_BARS="${DELAY_BARS:-1}"
export ALLOWED_HOURS="${ALLOWED_HOURS:-}"
if [[ -z "${ML_ARTIFACT_PATH:-}" && -f "data/ml/artifacts/latest/metadata.json" ]]; then
  export ML_ARTIFACT_PATH="data/ml/artifacts/latest"
fi
DRIFT_BASELINE_PATH="${DRIFT_BASELINE_PATH:-data/validation/drift/baseline_stats.json}"
DRIFT_REPORT_PATH="$OUT_DIR/feature_drift_report.json"
DRIFT_ONLINE_STATS_PATH="$OUT_DIR/feature_online_stats.json"
ALLOWLIST_JSON="$OUT_DIR/symbol_gating_recommendation.json"
ALLOWLIST_ENV="$OUT_DIR/symbol_gating.env"

SUMMARY_PATH="$OUT_DIR/timeframe_comparison_summary.json"
SUMMARY_PATH="$SUMMARY_PATH" ./scripts/timeframe_comparison.sh

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python - "$SUMMARY_PATH" "$ALLOWLIST_JSON" "$ALLOWLIST_ENV" <<'EOF_PY'
from __future__ import annotations

import sys

from auto_trader.analysis.gating import write_gating_artifacts

summary_path = sys.argv[1]
json_path = sys.argv[2]
env_path = sys.argv[3]
write_gating_artifacts(summary_path, json_path=json_path, env_path=env_path, timeframe="15m")
print(json_path)
print(env_path)
EOF_PY

set -a
source "$ALLOWLIST_ENV"
set +a

SUMMARY_PATH="$SUMMARY_PATH" ML_ARTIFACT_PATH="${ML_ARTIFACT_PATH:-}" ./scripts/timeframe_comparison.sh

LIMIT_SUMMARY_PATH="$OUT_DIR/timeframe_comparison_limit_summary.json"
SUMMARY_PATH="$LIMIT_SUMMARY_PATH" ORDER_MODE=limit ML_ARTIFACT_PATH="${ML_ARTIFACT_PATH:-}" ./scripts/timeframe_comparison.sh

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python - "$SUMMARY_PATH" "$ALLOWLIST_JSON" "$ALLOWLIST_ENV" <<'EOF_PY'
from __future__ import annotations

import sys

from auto_trader.analysis.gating import write_gating_artifacts

summary_path = sys.argv[1]
json_path = sys.argv[2]
env_path = sys.argv[3]
write_gating_artifacts(summary_path, json_path=json_path, env_path=env_path, timeframe="15m")
print(json_path)
print(env_path)
EOF_PY

set -a
source "$ALLOWLIST_ENV"
set +a

OUT_SUMMARY="$OUT_DIR/cost_grid_summary.jsonl" \
OUT_DIR="$OUT_DIR" \
ORDER_MODES="${ORDER_MODES:-market,limit}" \
FEE_RATES="${FEE_RATES:-0.0002,0.0003,0.0004}" \
SLIPPAGE_RATES="${SLIPPAGE_RATES:-0.0002,0.0005}" \
SPREAD_RATES="${SPREAD_RATES:-0.0001,0.0003}" \
DELAY_BARS_LIST="${DELAY_BARS_LIST:-0,1,2}" \
  LIMIT_BOOK_DEPTH_UNITS_LIST="${LIMIT_BOOK_DEPTH_UNITS_LIST:-0.0}" \
  LIMIT_QUEUE_AHEAD_UNITS_LIST="${LIMIT_QUEUE_AHEAD_UNITS_LIST:-0.02}" \
LIMIT_VOLUME_PARTICIPATION_RATE_LIST="${LIMIT_VOLUME_PARTICIPATION_RATE_LIST:-0.0}" \
TIMEFRAMES="$TIMEFRAMES" \
STRATEGIES="$STRATEGIES" \
ML_ARTIFACT_PATH="${ML_ARTIFACT_PATH:-}" \
./scripts/backtest_cost_grid.sh

LIMIT_DEFAULTS_JSON="$OUT_DIR/limit_defaults.json"
LIMIT_DEFAULTS_ENV="$OUT_DIR/limit_defaults.env"
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python - "$OUT_DIR/cost_grid_result.json" "$LIMIT_DEFAULTS_JSON" "$LIMIT_DEFAULTS_ENV" <<'EOF_PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
json_out = Path(sys.argv[2])
env_out = Path(sys.argv[3])
obj = json.loads(src.read_text())
best = obj.get("best", {})
payload = {
    "best": best,
    "source": str(src),
}
json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
env_out.write_text(
    "\n".join(
        [
            f"FEE_RATE={best.get('fee_rate', 0.0002)}",
            f"SLIPPAGE_RATE={best.get('slippage_rate', 0.0002)}",
            f"SPREAD_RATE={best.get('spread_rate', 0.0001)}",
            f"DELAY_BARS={best.get('delay_bars', 1)}",
            f"LIMIT_BOOK_DEPTH_UNITS={best.get('limit_book_depth_units', 0.0)}",
            f"LIMIT_QUEUE_AHEAD_UNITS={best.get('limit_queue_ahead_units', 0.02)}",
            f"LIMIT_VOLUME_PARTICIPATION_RATE={best.get('limit_volume_participation_rate', 0.0)}",
        ]
    )
    + "\n",
    encoding="utf-8",
)
print(json_out)
print(env_out)
EOF_PY

set -a
source "$LIMIT_DEFAULTS_ENV"
set +a

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python -m auto_trader.drift \
  --features-glob "data/features/*_15m_features.parquet" \
  --baseline-path "$DRIFT_BASELINE_PATH" \
  --report-path "$DRIFT_REPORT_PATH" \
  --online-stats-path "$DRIFT_ONLINE_STATS_PATH" \
  --write-baseline-if-missing true

python - \
  "$OUT_DIR/timeframe_comparison_summary.json" \
  "$OUT_DIR/timeframe_comparison_limit_summary.json" \
  "$OUT_DIR/weekly_revalidation_report.json" \
  "$DRIFT_REPORT_PATH" <<'EOF_PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

src = Path(sys.argv[1])
limit_src = Path(sys.argv[2])
dst = Path(sys.argv[3])
drift_path = Path(sys.argv[4])
drift = json.loads(drift_path.read_text()) if drift_path.exists() else {}

def load_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    obj = json.loads(path.read_text())
    return list(obj.get("rows", []))

def mean(rows: list[dict[str, object]], strategy: str, key: str) -> float:
    vals = [float(r.get(key, 0.0)) for r in rows if r.get("strategy") == strategy and r.get("timeframe") == "15m"]
    return sum(vals) / len(vals) if vals else 0.0

def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    trend_pf = mean(rows, "trend", "pf_mean")
    trend_exp = mean(rows, "trend", "expectancy_bps_mean")
    trend_pnl = mean(rows, "trend", "period_pnl_mean")
    trend_dd = mean(rows, "trend", "max_dd_mean")
    range_pf = mean(rows, "range", "pf_mean")
    range_exp = mean(rows, "range", "expectancy_bps_mean")
    range_pnl = mean(rows, "range", "period_pnl_mean")
    range_dd = mean(rows, "range", "max_dd_mean")
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
    return {
        "status": status,
        "metrics": {
            "trend": {"pf": trend_pf, "exp_bps": trend_exp, "period_pnl": trend_pnl, "dd": trend_dd},
            "range": {"pf": range_pf, "exp_bps": range_exp, "period_pnl": range_pnl, "dd": range_dd},
        },
        "checks": checks,
    }

market = summarize(load_rows(src))
limit = summarize(load_rows(limit_src))

status = "pass" if market["status"] == "pass" and limit["status"] == "pass" else "warn"
drift_status = str(drift.get("status", "unknown"))
if drift_status in {"warn", "fail"}:
    status = "warn"
out = {
    "schema_version": "1.2",
    "checked_at": datetime.now(UTC).isoformat(),
    "status": status,
    "metrics": market["metrics"],
    "limit_metrics": limit["metrics"],
    "checks": market["checks"],
    "limit_checks": limit["checks"],
    "market_status": market["status"],
    "limit_status": limit["status"],
    "summary_paths": {
        "market": str(src),
        "limit": str(limit_src),
    },
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
