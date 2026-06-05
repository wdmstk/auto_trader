#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT}"
TIMEFRAMES="${TIMEFRAMES:-5m,15m}"
STRATEGIES="${STRATEGIES:-range,trend}"
FOLDS="${FOLDS:-4}"
FEE_RATES="${FEE_RATES:-0.0002,0.0004}"
SLIPPAGE_RATES="${SLIPPAGE_RATES:-0.0002,0.0005}"
SPREAD_RATES="${SPREAD_RATES:-0.0001,0.0003}"
DELAY_BARS_LIST="${DELAY_BARS_LIST:-0,1}"
ORDER_MODES="${ORDER_MODES:-market}"
OUT_DIR="${OUT_DIR:-data/validation/cost_grid}"
OUT_SUMMARY="${OUT_SUMMARY:-$OUT_DIR/cost_grid_summary.jsonl}"
PARALLEL_JOBS="${PARALLEL_JOBS:-auto}"
LIMIT_BOOK_DEPTH_UNITS_LIST="${LIMIT_BOOK_DEPTH_UNITS_LIST:-${LIMIT_BOOK_DEPTH_UNITS:-0.0}}"
LIMIT_QUEUE_AHEAD_UNITS_LIST="${LIMIT_QUEUE_AHEAD_UNITS_LIST:-${LIMIT_QUEUE_AHEAD_UNITS:-0.02}}"
LIMIT_VOLUME_PARTICIPATION_RATE_LIST="${LIMIT_VOLUME_PARTICIPATION_RATE_LIST:-${LIMIT_VOLUME_PARTICIPATION_RATE:-0.0}}"

if [[ "$PARALLEL_JOBS" == "auto" ]]; then
  if command -v nproc >/dev/null 2>&1; then
    cpu_count="$(nproc)"
  else
    cpu_count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
  fi
  # Keep one core free for responsiveness, and cap to avoid I/O thrash.
  if [[ "$cpu_count" -le 2 ]]; then
    PARALLEL_JOBS=1
  else
    PARALLEL_JOBS=$((cpu_count - 1))
  fi
  if [[ "$PARALLEL_JOBS" -gt 8 ]]; then
    PARALLEL_JOBS=8
  fi
fi

mkdir -p "$OUT_DIR"
: > "$OUT_SUMMARY"
TMP_DIR="$OUT_DIR/.tmp_cost_grid"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

echo "== backtest cost grid =="
echo "symbols=$SYMBOLS timeframes=$TIMEFRAMES strategies=$STRATEGIES"
echo "order_modes=$ORDER_MODES fee=$FEE_RATES slip=$SLIPPAGE_RATES spread=$SPREAD_RATES delay=$DELAY_BARS_LIST"
echo "limit_depth=$LIMIT_BOOK_DEPTH_UNITS_LIST queue_ahead=$LIMIT_QUEUE_AHEAD_UNITS_LIST participation=$LIMIT_VOLUME_PARTICIPATION_RATE_LIST (standard sweep fixed defaults)"
echo "parallel_jobs=$PARALLEL_JOBS"

run_case() {
  local mode="$1"
  local fee="$2"
  local slip="$3"
  local spread="$4"
  local delay="$5"
  local book_depth="$6"
  local queue_ahead="$7"
  local volume_participation="$8"
  local summary_path="$OUT_DIR/timeframe_comparison_${mode}_fee${fee}_slip${slip}_spr${spread}_d${delay}_bd${book_depth}_qa${queue_ahead}_vp${volume_participation}.json"
  local row_path="$TMP_DIR/row_${mode}_fee${fee}_slip${slip}_spr${spread}_d${delay}_bd${book_depth}_qa${queue_ahead}_vp${volume_participation}.json"
  local case_root="$TMP_DIR/data_case_${mode}_fee${fee}_slip${slip}_spr${spread}_d${delay}_bd${book_depth}_qa${queue_ahead}_vp${volume_participation}"

  mkdir -p "$case_root/parquet"
  for symbol in ${SYMBOLS//,/ }; do
    ln -sf "$ROOT_DIR/data/parquet/${symbol}_1m.parquet" "$case_root/parquet/${symbol}_1m.parquet"
  done

  FEE_RATE="$fee" \
  SLIPPAGE_RATE="$slip" \
  SPREAD_RATE="$spread" \
  DELAY_BARS="$delay" \
  ORDER_MODE="$mode" \
  LIMIT_BOOK_DEPTH_UNITS="$book_depth" \
  LIMIT_QUEUE_AHEAD_UNITS="$queue_ahead" \
  LIMIT_VOLUME_PARTICIPATION_RATE="$volume_participation" \
  DATA_ROOT="$case_root" \
  SYMBOLS="$SYMBOLS" \
  TIMEFRAMES="$TIMEFRAMES" \
  STRATEGIES="$STRATEGIES" \
  FOLDS="$FOLDS" \
  RANGE_REQUIRE_REVERSAL_CANDLE="${RANGE_REQUIRE_REVERSAL_CANDLE:-false}" \
  RANGE_WICK_RATIO_MIN="${RANGE_WICK_RATIO_MIN:-0.3}" \
  SUMMARY_PATH="$summary_path" \
  ML_ARTIFACT_PATH="${ML_ARTIFACT_PATH:-}" \
  ./scripts/timeframe_comparison.sh >/dev/null

  "$PYTHON_BIN" - "$summary_path" "$mode" "$fee" "$slip" "$spread" "$delay" "$book_depth" "$queue_ahead" "$volume_participation" "$row_path" <<'PY'
import json
import statistics as s
import sys
from pathlib import Path

path = Path(sys.argv[1])
mode = str(sys.argv[2])
fee = float(sys.argv[3])
slip = float(sys.argv[4])
spr = float(sys.argv[5])
delay = int(sys.argv[6])
book_depth = float(sys.argv[7])
queue_ahead = float(sys.argv[8])
volume_participation = float(sys.argv[9])
row_path = Path(sys.argv[10])
obj = json.loads(path.read_text())
rows = obj["rows"]

def mean_of(strategy: str, timeframe: str, key: str) -> float:
    vals = [r[key] for r in rows if r["strategy"] == strategy and r["timeframe"] == timeframe]
    return float(s.mean(vals)) if vals else 0.0

result = {
    "order_mode": mode,
    "fee_rate": fee,
    "slippage_rate": slip,
    "spread_rate": spr,
    "delay_bars": delay,
    "limit_book_depth_units": book_depth,
    "limit_queue_ahead_units": queue_ahead,
    "limit_volume_participation_rate": volume_participation,
    "trend_15m_expectancy_bps": mean_of("trend", "15m", "expectancy_bps_mean"),
    "trend_15m_period_pnl": mean_of("trend", "15m", "period_pnl_mean"),
    "trend_15m_pf": mean_of("trend", "15m", "pf_mean"),
    "trend_15m_dd": mean_of("trend", "15m", "max_dd_mean"),
    "trend_15m_limit_fill_rate": mean_of("trend", "15m", "limit_fill_rate_mean"),
    "trend_15m_limit_taker_like_rate": mean_of("trend", "15m", "limit_taker_like_rate_mean"),
    "range_15m_expectancy_bps": mean_of("range", "15m", "expectancy_bps_mean"),
    "range_15m_period_pnl": mean_of("range", "15m", "period_pnl_mean"),
    "range_15m_pf": mean_of("range", "15m", "pf_mean"),
    "range_15m_dd": mean_of("range", "15m", "max_dd_mean"),
    "range_15m_limit_fill_rate": mean_of("range", "15m", "limit_fill_rate_mean"),
    "range_15m_limit_taker_like_rate": mean_of("range", "15m", "limit_taker_like_rate_mean"),
}
row_path.write_text(json.dumps(result, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

running=0
for mode in ${ORDER_MODES//,/ }; do
  for fee in ${FEE_RATES//,/ }; do
    for slip in ${SLIPPAGE_RATES//,/ }; do
      for spread in ${SPREAD_RATES//,/ }; do
        for delay in ${DELAY_BARS_LIST//,/ }; do
          for book_depth in ${LIMIT_BOOK_DEPTH_UNITS_LIST//,/ }; do
            for queue_ahead in ${LIMIT_QUEUE_AHEAD_UNITS_LIST//,/ }; do
              for volume_participation in ${LIMIT_VOLUME_PARTICIPATION_RATE_LIST//,/ }; do
                run_case \
                  "$mode" \
                  "$fee" \
                  "$slip" \
                  "$spread" \
                  "$delay" \
                  "$book_depth" \
                  "$queue_ahead" \
                  "$volume_participation" &
                running=$((running + 1))
                if [[ "$running" -ge "$PARALLEL_JOBS" ]]; then
                  wait -n
                  running=$((running - 1))
                fi
              done
            done
          done
        done
      done
    done
  done
done
wait

cat "$TMP_DIR"/row_*.json > "$OUT_SUMMARY"

"$PYTHON_BIN" - "$OUT_SUMMARY" <<'PY'
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
if not rows:
    raise SystemExit("no rows")

def score(r):
    return (
        r["trend_15m_expectancy_bps"] + r["range_15m_expectancy_bps"],
        r["trend_15m_pf"] + r["range_15m_pf"],
        -(r["trend_15m_dd"] + r["range_15m_dd"]),
        r["trend_15m_period_pnl"] + r["range_15m_period_pnl"],
        -(
            max(r["trend_15m_limit_taker_like_rate"], 0.0)
            + max(r["range_15m_limit_taker_like_rate"], 0.0)
        ),
    )

best = sorted(rows, key=score, reverse=True)[0]
out = {
    "best": best,
    "rows": rows,
}
result_path = p.with_name("cost_grid_result.json")
result_path.write_text(json.dumps(out, ensure_ascii=True, indent=2), encoding="utf-8")
print(result_path)
PY

echo "done: $OUT_SUMMARY"
