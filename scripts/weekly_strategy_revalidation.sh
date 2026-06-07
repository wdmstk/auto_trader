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
export RANGE_WICK_RATIO_MIN="${RANGE_WICK_RATIO_MIN:-0.2}"
export RANGE_REENTRY_COOLDOWN_BARS="${RANGE_REENTRY_COOLDOWN_BARS:-2}"
export RANGE_ENABLED_SYMBOLS="${RANGE_ENABLED_SYMBOLS:-SOLUSDT,XRPUSDT}"
export RANGE_PROBE_SYMBOLS="${RANGE_PROBE_SYMBOLS:-BNBUSDT}"
export RANGE_PROBE_TIMEFRAMES="${RANGE_PROBE_TIMEFRAMES:-15m,30m,1h}"

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
CANDIDATE_REPORT_PATH="$OUT_DIR/candidate_report.json"
RANGE_PROBE_REPORT_DIR="$OUT_DIR/range_probe"
RANGE_PROBE_REPORT_PATH="$RANGE_PROBE_REPORT_DIR/candidate_report.json"

SUMMARY_PATH="$OUT_DIR/timeframe_comparison_summary.json"
SUMMARY_PATH="$SUMMARY_PATH" CANDIDATE_REPORT_PATH="$CANDIDATE_REPORT_PATH" ./scripts/timeframe_comparison.sh

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

SUMMARY_PATH="$SUMMARY_PATH" \
CANDIDATE_REPORT_PATH="$CANDIDATE_REPORT_PATH" \
ML_ARTIFACT_PATH="${ML_ARTIFACT_PATH:-}" \
./scripts/timeframe_comparison.sh

LIMIT_SUMMARY_PATH="$OUT_DIR/timeframe_comparison_limit_summary.json"
SUMMARY_PATH="$LIMIT_SUMMARY_PATH" \
CANDIDATE_REPORT_PATH="$OUT_DIR/candidate_report_limit.json" \
ORDER_MODE=limit \
ML_ARTIFACT_PATH="${ML_ARTIFACT_PATH:-}" \
./scripts/timeframe_comparison.sh

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

if [[ -n "${RANGE_PROBE_SYMBOLS:-}" ]]; then
  SUMMARY_PATH="$RANGE_PROBE_REPORT_DIR/timeframe_comparison_summary.json" \
  CANDIDATE_REPORT_PATH="$RANGE_PROBE_REPORT_PATH" \
  OUT_DIR="$RANGE_PROBE_REPORT_DIR" \
  SYMBOLS="$RANGE_PROBE_SYMBOLS" \
  TIMEFRAMES="$RANGE_PROBE_TIMEFRAMES" \
  STRATEGIES=range \
  RANGE_ENABLED_SYMBOLS="$RANGE_PROBE_SYMBOLS" \
  RANGE_REQUIRE_REVERSAL_CANDLE=false \
  RANGE_WICK_RATIO_MIN=0.2 \
  RANGE_REENTRY_COOLDOWN_BARS=2 \
  ./scripts/timeframe_candidate_scan.sh
fi

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
  "$OUT_DIR/symbol_gating_recommendation.json" \
  "$CANDIDATE_REPORT_PATH" \
  "$RANGE_PROBE_REPORT_PATH" \
  "$OUT_DIR/weekly_revalidation_report.json" \
  "$DRIFT_REPORT_PATH" <<'EOF_PY'
from __future__ import annotations

import sys
from pathlib import Path

market_summary = Path(sys.argv[1])
limit_summary = Path(sys.argv[2])
gating_path = Path(sys.argv[3])
candidate_path = Path(sys.argv[4])
probe_candidate_path = Path(sys.argv[5])
dst = Path(sys.argv[6])
drift_path = Path(sys.argv[7])

import json

from auto_trader.analysis.revalidation import build_weekly_revalidation_report
from auto_trader.analysis.trade_routes import build_trade_route_selection

report = build_weekly_revalidation_report(
    market_summary,
    limit_summary,
    symbol_gating=gating_path,
    candidate_report=candidate_path,
    drift_report=drift_path,
    timeframe="15m",
)
if probe_candidate_path.exists():
    try:
        report["range_probe_candidates"] = json.loads(probe_candidate_path.read_text(encoding="utf-8"))
    except Exception:
        report["range_probe_candidates"] = {"status": "warn", "path": str(probe_candidate_path)}
route_selection = build_trade_route_selection(report, default_timeframe="15m")
selection = report.get("selection", {})
if not isinstance(selection, dict):
    selection = {}
selection.update(route_selection)
report["selection"] = selection
report["summary_paths"] = {
    "market": str(market_summary),
    "limit": str(limit_summary),
}
dst.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
print(dst)
EOF_PY

echo "done: $OUT_DIR"
