#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
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
export WEEKLY_SCAN_PARALLEL="${WEEKLY_SCAN_PARALLEL:-4}"
export WEEKLY_ROUTE_PARALLEL="${WEEKLY_ROUTE_PARALLEL:-4}"
export WEEKLY_ROUTE_DATA_PARALLEL="${WEEKLY_ROUTE_DATA_PARALLEL:-1}"
RUN_COST_GRID="${RUN_COST_GRID:-0}"
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
STATISTICAL_DIR="${STATISTICAL_DIR:-data/validation/statistical_qualification}"
STATISTICAL_REPORT_PATH="$STATISTICAL_DIR/qualification_report.json"
STATISTICAL_MANIFEST_PATH="$STATISTICAL_DIR/frozen_manifest.json"
ROUTE_SELECTION_PATH="${ROUTE_SELECTION_PATH:-}"
RISK_EVAL_PATH="${RISK_EVAL_PATH:-data/risk/risk_eval.parquet}"
STATISTICAL_GATE_MODE="${STATISTICAL_GATE_MODE:-soft}"
RUN_ID="${RUN_ID:-${PIPELINE_RUN_ID:-weekly-revalidation-$(TZ=UTC date +%Y%m%dT%H%M%SZ)}}"
MANIFEST_SUMMARY_PATH="$OUT_DIR/manifest_route_summary.json"
MANIFEST_CANDIDATE_REPORT_PATH="$OUT_DIR/manifest_candidate_report.json"
MANIFEST_DATA_ROOT="${MANIFEST_DATA_ROOT:-$OUT_DIR/manifest_route_run_data}"

SUMMARY_PATH="$OUT_DIR/timeframe_comparison_summary.json"
echo "weekly_parallel: scan=$WEEKLY_SCAN_PARALLEL route=$WEEKLY_ROUTE_PARALLEL route_data=$WEEKLY_ROUTE_DATA_PARALLEL"
echo "statistical_gate_mode=$STATISTICAL_GATE_MODE"
echo "run_id=$RUN_ID"
SUMMARY_PATH="$SUMMARY_PATH" \
CANDIDATE_REPORT_PATH="$CANDIDATE_REPORT_PATH" \
PARALLEL="$WEEKLY_SCAN_PARALLEL" \
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

SUMMARY_PATH="$SUMMARY_PATH" \
CANDIDATE_REPORT_PATH="$CANDIDATE_REPORT_PATH" \
ML_ARTIFACT_PATH="${ML_ARTIFACT_PATH:-}" \
PARALLEL="$WEEKLY_SCAN_PARALLEL" \
./scripts/timeframe_comparison.sh

SELECTED_MARKET_SUMMARY_PATH="$SUMMARY_PATH"
SELECTED_CANDIDATE_REPORT_PATH="$CANDIDATE_REPORT_PATH"
SELECTED_ANALYSIS_DIR="data/analysis"

if [[ -n "$ROUTE_SELECTION_PATH" && -f "$ROUTE_SELECTION_PATH" ]]; then
  PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
  ROUTE_SELECTION_PATH="$ROUTE_SELECTION_PATH" \
  OUT_DIR="$OUT_DIR" \
  MANIFEST_SUMMARY_PATH="$MANIFEST_SUMMARY_PATH" \
  MANIFEST_CANDIDATE_REPORT_PATH="$MANIFEST_CANDIDATE_REPORT_PATH" \
  MANIFEST_DATA_ROOT="$MANIFEST_DATA_ROOT" \
  BASE_DATA_ROOT="${BASE_DATA_ROOT:-data}" \
  "$PYTHON_BIN" ./scripts/route_manifest_timeframe_comparison.py
  SELECTED_MARKET_SUMMARY_PATH="$MANIFEST_SUMMARY_PATH"
  SELECTED_CANDIDATE_REPORT_PATH="$MANIFEST_CANDIDATE_REPORT_PATH"
  SELECTED_ANALYSIS_DIR="$MANIFEST_DATA_ROOT/analysis"
fi

mkdir -p "$STATISTICAL_DIR"
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python - "$SELECTED_MARKET_SUMMARY_PATH" "$SELECTED_ANALYSIS_DIR" "$STATISTICAL_MANIFEST_PATH" "$STATISTICAL_REPORT_PATH" "$DELAY_BARS" "$RUN_ID" <<'EOF_PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from auto_trader.analysis.statistical import build_statistical_qualification

report = build_statistical_qualification(
    sys.argv[1],
    analysis_dir=sys.argv[2],
    manifest_path=sys.argv[3],
    report_path=sys.argv[4],
    execution_delay_bars=int(sys.argv[5]),
    run_id=sys.argv[6],
    generated_at=datetime.now(UTC).isoformat(),
)
print(json.dumps({"status": report["status"], "report_path": sys.argv[4]}, ensure_ascii=True))
EOF_PY

LIMIT_SUMMARY_PATH="$OUT_DIR/timeframe_comparison_limit_summary.json"
SUMMARY_PATH="$LIMIT_SUMMARY_PATH" \
CANDIDATE_REPORT_PATH="$OUT_DIR/candidate_report_limit.json" \
ORDER_MODE=limit \
ML_ARTIFACT_PATH="${ML_ARTIFACT_PATH:-}" \
PARALLEL="$WEEKLY_SCAN_PARALLEL" \
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
LIMIT_DEFAULTS_JSON="$OUT_DIR/limit_defaults.json"
LIMIT_DEFAULTS_ENV="$OUT_DIR/limit_defaults.env"

if [[ "$RUN_COST_GRID" == "1" ]]; then
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
else
  cat > "$LIMIT_DEFAULTS_ENV" <<EOF_ENV
FEE_RATE=$FEE_RATE
SLIPPAGE_RATE=$SLIPPAGE_RATE
SPREAD_RATE=$SPREAD_RATE
DELAY_BARS=$DELAY_BARS
LIMIT_BOOK_DEPTH_UNITS=${LIMIT_BOOK_DEPTH_UNITS:-0.0}
LIMIT_QUEUE_AHEAD_UNITS=${LIMIT_QUEUE_AHEAD_UNITS:-0.02}
LIMIT_VOLUME_PARTICIPATION_RATE=${LIMIT_VOLUME_PARTICIPATION_RATE:-0.0}
EOF_ENV
  cat > "$LIMIT_DEFAULTS_JSON" <<EOF_JSON
{
  "best": {
    "fee_rate": $FEE_RATE,
    "slippage_rate": $SLIPPAGE_RATE,
    "spread_rate": $SPREAD_RATE,
    "delay_bars": $DELAY_BARS,
    "limit_book_depth_units": ${LIMIT_BOOK_DEPTH_UNITS:-0.0},
    "limit_queue_ahead_units": ${LIMIT_QUEUE_AHEAD_UNITS:-0.02},
    "limit_volume_participation_rate": ${LIMIT_VOLUME_PARTICIPATION_RATE:-0.0}
  },
  "source": "skipped_cost_grid"
}
EOF_JSON
fi

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
  PARALLEL="$WEEKLY_SCAN_PARALLEL" \
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
  "$SELECTED_MARKET_SUMMARY_PATH" \
  "$OUT_DIR/timeframe_comparison_limit_summary.json" \
  "$OUT_DIR/symbol_gating_recommendation.json" \
  "$SELECTED_CANDIDATE_REPORT_PATH" \
  "$RANGE_PROBE_REPORT_PATH" \
  "$OUT_DIR/weekly_revalidation_report.json" \
  "$DRIFT_REPORT_PATH" \
  "$STATISTICAL_REPORT_PATH" \
  "$ROUTE_SELECTION_PATH" \
  "$RISK_EVAL_PATH" \
  "$STATISTICAL_GATE_MODE" \
  "$RUN_ID" <<'EOF_PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

market_summary = Path(sys.argv[1])
limit_summary = Path(sys.argv[2])
gating_path = Path(sys.argv[3])
candidate_path = Path(sys.argv[4])
probe_candidate_path = Path(sys.argv[5])
dst = Path(sys.argv[6])
drift_path = Path(sys.argv[7])
statistical_path = Path(sys.argv[8])
route_selection_path = Path(sys.argv[9]) if len(sys.argv) > 9 and sys.argv[9] else None
risk_eval_path = Path(sys.argv[10]) if len(sys.argv) > 10 and sys.argv[10] else None
statistical_gate_mode = sys.argv[11] if len(sys.argv) > 11 else "soft"
run_id = sys.argv[12] if len(sys.argv) > 12 else ""

import json
from datetime import UTC, datetime

from auto_trader.analysis.revalidation import build_weekly_revalidation_report
from auto_trader.analysis.trade_routes import (
    build_trade_route_selection,
    validate_trade_route_selection,
)

report = build_weekly_revalidation_report(
    market_summary,
    limit_summary,
    symbol_gating=gating_path,
    candidate_report=candidate_path,
    drift_report=drift_path,
    statistical_report=statistical_path,
    route_selection=route_selection_path if route_selection_path and route_selection_path.exists() else None,
    portfolio_risk_eval=risk_eval_path if risk_eval_path and risk_eval_path.exists() else None,
    timeframe="15m",
    statistical_gate_mode=statistical_gate_mode,
    run_id=run_id,
    generated_at=datetime.now(UTC).isoformat(),
)
if probe_candidate_path.exists():
    try:
        report["range_probe_candidates"] = json.loads(probe_candidate_path.read_text(encoding="utf-8"))
    except Exception:
        report["range_probe_candidates"] = {"status": "warn", "path": str(probe_candidate_path)}
route_selection = build_trade_route_selection(
    report,
    default_timeframe="15m",
    seed_manifest=route_selection_path if route_selection_path and route_selection_path.exists() else None,
    statistical_gate_mode=statistical_gate_mode,
)
selection = report.get("selection", {})
if not isinstance(selection, dict):
    selection = {}
selection.update(route_selection)
validate_trade_route_selection(selection)
report["selection"] = selection
report["summary_paths"] = {
    "market": str(market_summary),
    "limit": str(limit_summary),
    "drift": str(drift_path),
    "statistical": str(statistical_path),
}


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.tmp.{os.getpid()}"
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


_atomic_write_text(dst, json.dumps(report, ensure_ascii=True, indent=2))
print(dst)
EOF_PY

RUN_ID="$RUN_ID" \
QUALIFICATION_REPORT_PATH="$STATISTICAL_REPORT_PATH" \
ANALYSIS_DIR="$SELECTED_ANALYSIS_DIR" \
OUTPUT_JSON="$OUT_DIR/statistical_fail_diagnostics.json" \
OUTPUT_MD="$OUT_DIR/statistical_fail_diagnostics.md" \
./scripts/statistical_fail_diagnostics_report.sh

echo "done: $OUT_DIR"
