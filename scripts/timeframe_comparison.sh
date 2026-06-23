#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "python interpreter not found" >&2
    exit 127
  fi
fi
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
DATA_ROOT="${DATA_ROOT:-data}"
BASE_DATA_ROOT="${BASE_DATA_ROOT:-data}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT}"
TIMEFRAMES="${TIMEFRAMES:-1m,5m,15m}"
STRATEGIES="${STRATEGIES:-range,trend}"
FOLDS="${FOLDS:-4}"
OUTPUT_DIR="${OUTPUT_DIR:-$DATA_ROOT/validation/timeframe_eval}"
SUMMARY_PATH="${SUMMARY_PATH:-$OUTPUT_DIR/timeframe_comparison_summary.json}"
RANGE_RSI_MIN="${RANGE_RSI_MIN:-40}"
RANGE_RSI_MAX="${RANGE_RSI_MAX:-50}"
RANGE_WICK_RATIO_MIN="${RANGE_WICK_RATIO_MIN:-0.5}"
RANGE_MEAN_REVERSION_DISTANCE_MAX="${RANGE_MEAN_REVERSION_DISTANCE_MAX:--0.1}"
RANGE_EXIT_MEAN_REVERSION_NEUTRAL_ABS="${RANGE_EXIT_MEAN_REVERSION_NEUTRAL_ABS:-0.05}"
RANGE_DEFAULT_POSITION_SIZE_RATIO="${RANGE_DEFAULT_POSITION_SIZE_RATIO:-0.1}"
RANGE_REQUIRE_REVERSAL_CANDLE="${RANGE_REQUIRE_REVERSAL_CANDLE:-true}"
RANGE_MIN_ENTRY_SCORE="${RANGE_MIN_ENTRY_SCORE:-1.0}"
RANGE_REENTRY_COOLDOWN_BARS="${RANGE_REENTRY_COOLDOWN_BARS:-0}"
RANGE_MAX_HOLD_BARS="${RANGE_MAX_HOLD_BARS:-0}"
RANGE_ENABLED_SYMBOLS="${RANGE_ENABLED_SYMBOLS:-}"
RANGE_BB_POSITION_MAX="${RANGE_BB_POSITION_MAX:-0.35}"
RANGE_VOLUME_SPIKE_THRESHOLD="${RANGE_VOLUME_SPIKE_THRESHOLD:-1.3}"
RANGE_PRICE_VS_RECENT_LOW_MAX="${RANGE_PRICE_VS_RECENT_LOW_MAX:-1.5}"
RANGE_W_RSI="${RANGE_W_RSI:-1.0}"
RANGE_W_WICK="${RANGE_W_WICK:-1.0}"
RANGE_W_MR="${RANGE_W_MR:-1.5}"
RANGE_W_BB_POS="${RANGE_W_BB_POS:-2.0}"
RANGE_W_VOL="${RANGE_W_VOL:-1.0}"
RANGE_W_REVERSAL_BONUS="${RANGE_W_REVERSAL_BONUS:-0.5}"
RANGE_EXIT_ATR_TRAIL_MULTIPLIER="${RANGE_EXIT_ATR_TRAIL_MULTIPLIER:-2.0}"
TREND_MIN_ENTRY_SCORE="${TREND_MIN_ENTRY_SCORE:-1.0}"
TREND_BREAKOUT_PERSISTENCE_MIN="${TREND_BREAKOUT_PERSISTENCE_MIN:-0.6}"
TREND_MOMENTUM_PERSISTENCE_MIN="${TREND_MOMENTUM_PERSISTENCE_MIN:-0.5}"
TREND_PULLBACK_SHALLOWNESS_MIN="${TREND_PULLBACK_SHALLOWNESS_MIN:-0.5}"
TREND_HIGHER_HIGH_PERSISTENCE_MIN="${TREND_HIGHER_HIGH_PERSISTENCE_MIN:-0.5}"
TREND_EFFICIENCY_EXIT_THRESHOLD="${TREND_EFFICIENCY_EXIT_THRESHOLD:-0.1}"
TREND_REENTRY_COOLDOWN_BARS="${TREND_REENTRY_COOLDOWN_BARS:-0}"
TREND_MAX_HOLD_BARS="${TREND_MAX_HOLD_BARS:-0}"
TREND_ENABLED_SYMBOLS="${TREND_ENABLED_SYMBOLS:-}"
REGIME_TREND_ADX_THRESHOLD="${REGIME_TREND_ADX_THRESHOLD:-25.0}"
REGIME_TREND_BREAKOUT_PERSISTENCE_MIN_BARS="${REGIME_TREND_BREAKOUT_PERSISTENCE_MIN_BARS:-3}"
REGIME_RANGE_BB_WIDTH_PERCENTILE_MAX="${REGIME_RANGE_BB_WIDTH_PERCENTILE_MAX:-40.0}"
REGIME_RANGE_ADX_MAX="${REGIME_RANGE_ADX_MAX:-20.0}"
MIN_REGIME_HOLD_BARS="${MIN_REGIME_HOLD_BARS:-3}"
HIGH_VOL_COOLDOWN_BARS="${HIGH_VOL_COOLDOWN_BARS:-5}"
DRIFT_REPORT_PATH="${DRIFT_REPORT_PATH:-}"
ML_ARTIFACT_PATH="${ML_ARTIFACT_PATH:-}"
ALLOWED_HOURS="${ALLOWED_HOURS:-}"
CANDIDATE_REPORT_PATH="${CANDIDATE_REPORT_PATH:-}"
FEE_RATE="${FEE_RATE:-0.0004}"
SLIPPAGE_RATE="${SLIPPAGE_RATE:-0.0005}"
SPREAD_RATE="${SPREAD_RATE:-0.0003}"
DELAY_BARS="${DELAY_BARS:-1}"
ORDER_MODE="${ORDER_MODE:-market}"
MAKER_FEE_RATE="${MAKER_FEE_RATE:-0.0}"
TAKER_FEE_RATE="${TAKER_FEE_RATE:-0.0}"
LIMIT_OFFSET_RATE="${LIMIT_OFFSET_RATE:-0.0}"
LIMIT_PARTIAL_FILL_RATIO="${LIMIT_PARTIAL_FILL_RATIO:-0.1}"
PARALLEL="${PARALLEL:-1}"
SKIP_FEATURE_CACHE="${SKIP_FEATURE_CACHE:-0}"
CORE_MIN_PF="${CORE_MIN_PF:-1.2}"
CORE_MIN_EXPECTANCY_BPS="${CORE_MIN_EXPECTANCY_BPS:-0.0}"
CORE_MIN_PERIOD_PNL="${CORE_MIN_PERIOD_PNL:-0.0}"
CORE_MAX_DRAWDOWN="${CORE_MAX_DRAWDOWN:-0.08}"
PROBE_MIN_PF="${PROBE_MIN_PF:-0.8}"
PROBE_MIN_EXPECTANCY_BPS="${PROBE_MIN_EXPECTANCY_BPS:-0.0}"
PROBE_MIN_PERIOD_PNL="${PROBE_MIN_PERIOD_PNL:-0.0}"
PROBE_MAX_DRAWDOWN="${PROBE_MAX_DRAWDOWN:-0.15}"
MIN_CLOSED_TRADES="${MIN_CLOSED_TRADES:-1.0}"

mkdir -p "$OUTPUT_DIR" \
  "$DATA_ROOT/parquet" \
  "$DATA_ROOT/features" \
  "$DATA_ROOT/regime" \
  "$DATA_ROOT/signals" \
  "$DATA_ROOT/analysis"

mkdir -p "$(dirname "$SUMMARY_PATH")"
if [[ -n "$CANDIDATE_REPORT_PATH" ]]; then
  mkdir -p "$(dirname "$CANDIDATE_REPORT_PATH")"
fi

echo "== timeframe comparison =="
echo "symbols=$SYMBOLS timeframes=$TIMEFRAMES strategies=$STRATEGIES folds=$FOLDS parallel=$PARALLEL"
echo "range_cfg: rsi=[$RANGE_RSI_MIN,$RANGE_RSI_MAX] wick>=$RANGE_WICK_RATIO_MIN mr<=$RANGE_MEAN_REVERSION_DISTANCE_MAX require_reversal=$RANGE_REQUIRE_REVERSAL_CANDLE"
echo "range_gate: min_score=$RANGE_MIN_ENTRY_SCORE cooldown=$RANGE_REENTRY_COOLDOWN_BARS max_hold=$RANGE_MAX_HOLD_BARS enabled=[$RANGE_ENABLED_SYMBOLS]"
echo "trend_gate: min_score=$TREND_MIN_ENTRY_SCORE breakout>=$TREND_BREAKOUT_PERSISTENCE_MIN momentum>=$TREND_MOMENTUM_PERSISTENCE_MIN pullback>=$TREND_PULLBACK_SHALLOWNESS_MIN higher_high>=$TREND_HIGHER_HIGH_PERSISTENCE_MIN exit_threshold=$TREND_EFFICIENCY_EXIT_THRESHOLD cooldown=$TREND_REENTRY_COOLDOWN_BARS max_hold=$TREND_MAX_HOLD_BARS enabled=[$TREND_ENABLED_SYMBOLS]"
echo "regime_cfg: trend_adx>=$REGIME_TREND_ADX_THRESHOLD trend_breakout_min_bars=$REGIME_TREND_BREAKOUT_PERSISTENCE_MIN_BARS range_bb_width_pct<=$REGIME_RANGE_BB_WIDTH_PERCENTILE_MAX range_adx<=$REGIME_RANGE_ADX_MAX min_hold=$MIN_REGIME_HOLD_BARS high_vol_cooldown=$HIGH_VOL_COOLDOWN_BARS"
echo "session_gate: allowed_hours=${ALLOWED_HOURS:-off}"
echo "backtest_cfg: mode=$ORDER_MODE fee=$FEE_RATE maker=$MAKER_FEE_RATE taker=$TAKER_FEE_RATE slippage=$SLIPPAGE_RATE spread=$SPREAD_RATE delay=$DELAY_BARS"
echo "candidate_thresholds: core_pf>=$CORE_MIN_PF core_expbps>$CORE_MIN_EXPECTANCY_BPS core_pnl>$CORE_MIN_PERIOD_PNL core_dd<=$CORE_MAX_DRAWDOWN probe_pf>=$PROBE_MIN_PF probe_dd<=$PROBE_MAX_DRAWDOWN trades>=$MIN_CLOSED_TRADES"
echo "data_roots: base=$BASE_DATA_ROOT run=$DATA_ROOT skip_feature_cache=$SKIP_FEATURE_CACHE"

run_symbol_timeframe() {
  local symbol="$1"
  local timeframe="$2"
  local base_1m="$BASE_DATA_ROOT/parquet/${symbol}_1m.parquet"
  local base_timeframe_ohlcv="$BASE_DATA_ROOT/parquet/${symbol}_${timeframe}.parquet"
  local target_ohlcv="$DATA_ROOT/parquet/${symbol}_${timeframe}.parquet"
  local base_feature_path="$BASE_DATA_ROOT/features/${symbol}_${timeframe}_features.parquet"
  local feature_path="$DATA_ROOT/features/${symbol}_${timeframe}_features.parquet"
  local base_regime_path="$BASE_DATA_ROOT/regime/${symbol}_${timeframe}_regime.parquet"
  local regime_path="$DATA_ROOT/regime/${symbol}_${timeframe}_regime.parquet"

  if [[ ! -f "$base_1m" ]]; then
    echo "missing base 1m data: $base_1m" >&2
    return 1
  fi

  echo "[START] $symbol/$timeframe"
  if [[ "$timeframe" == "1m" ]]; then
    if [[ ! -f "$target_ohlcv" ]]; then
      cp "$base_1m" "$target_ohlcv"
    fi
  else
    if [[ ! -f "$target_ohlcv" && -f "$base_timeframe_ohlcv" ]]; then
      cp "$base_timeframe_ohlcv" "$target_ohlcv"
    elif [[ ! -f "$target_ohlcv" ]]; then
      "$PYTHON_BIN" - "$base_1m" "$target_ohlcv" "$timeframe" <<'PY'
import sys
from pathlib import Path
import pandas as pd

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
timeframe = sys.argv[3]
rule_map = {"5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h"}
if timeframe not in rule_map:
    raise SystemExit(f"unsupported timeframe: {timeframe}")

df = pd.read_parquet(src).copy()
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df = df.sort_values("timestamp")
symbol = str(df["symbol"].iloc[0])

res = (
    df.set_index("timestamp")
    .resample(rule_map[timeframe], label="right", closed="right")
    .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    .dropna(subset=["open", "high", "low", "close"])
    .reset_index()
)
res["symbol"] = symbol
res["timeframe"] = timeframe
res = res[["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"]]
res.to_parquet(dst, index=False)
print(f"saved={dst} rows={len(res)}")
PY
    fi
  fi

  if [[ "$SKIP_FEATURE_CACHE" == "1" && -f "$feature_path" ]]; then
    rm -f "$feature_path"
  fi
  if [[ ! -f "$feature_path" && -f "$base_feature_path" && "$SKIP_FEATURE_CACHE" != "1" ]]; then
    cp "$base_feature_path" "$feature_path"
  elif [[ ! -f "$feature_path" ]]; then
    "$PYTHON_BIN" -m auto_trader.features \
      --ohlcv-path "$target_ohlcv" \
      --symbol "$symbol" \
      --timeframe "$timeframe" \
      --output-dir "$DATA_ROOT/features"
  fi

  if [[ ! -f "$regime_path" && -f "$base_regime_path" ]]; then
    cp "$base_regime_path" "$regime_path"
  elif [[ ! -f "$regime_path" ]]; then
    "$PYTHON_BIN" -m auto_trader.regime \
      --feature-path "$feature_path" \
      --symbol "$symbol" \
      --timeframe "$timeframe" \
      --output-dir "$DATA_ROOT/regime" \
      --trend-adx-threshold "$REGIME_TREND_ADX_THRESHOLD" \
      --trend-breakout-persistence-min-bars "$REGIME_TREND_BREAKOUT_PERSISTENCE_MIN_BARS" \
      --range-bb-width-percentile-max "$REGIME_RANGE_BB_WIDTH_PERCENTILE_MAX" \
      --range-adx-max "$REGIME_RANGE_ADX_MAX" \
      --min-regime-hold-bars "$MIN_REGIME_HOLD_BARS" \
      --high-vol-cooldown-bars "$HIGH_VOL_COOLDOWN_BARS"
  fi

  local strategy
  for strategy in ${STRATEGIES//,/ }; do
    if [[ "$strategy" == "range" ]]; then
      "$PYTHON_BIN" -m auto_trader.strategy \
        --strategy "$strategy" \
        --features-path "$feature_path" \
        --regime-path "$regime_path" \
        --symbol "$symbol" \
        --timeframe "$timeframe" \
        --output-dir "$DATA_ROOT/signals" \
        --range-rsi-min "$RANGE_RSI_MIN" \
        --range-rsi-max "$RANGE_RSI_MAX" \
        --range-wick-ratio-min "$RANGE_WICK_RATIO_MIN" \
        --range-mean-reversion-distance-max "$RANGE_MEAN_REVERSION_DISTANCE_MAX" \
        --range-exit-mean-reversion-neutral-abs "$RANGE_EXIT_MEAN_REVERSION_NEUTRAL_ABS" \
        --range-default-position-size-ratio "$RANGE_DEFAULT_POSITION_SIZE_RATIO" \
        --range-require-reversal-candle "$RANGE_REQUIRE_REVERSAL_CANDLE" \
        --range-min-entry-score "$RANGE_MIN_ENTRY_SCORE" \
        --range-reentry-cooldown-bars "$RANGE_REENTRY_COOLDOWN_BARS" \
        --range-max-hold-bars "$RANGE_MAX_HOLD_BARS" \
        --range-enabled-symbols "$RANGE_ENABLED_SYMBOLS" \
        --range-bb-position-max "$RANGE_BB_POSITION_MAX" \
        --range-volume-spike-threshold "$RANGE_VOLUME_SPIKE_THRESHOLD" \
        --range-price-vs-recent-low-max "$RANGE_PRICE_VS_RECENT_LOW_MAX" \
        --range-w-rsi "$RANGE_W_RSI" \
        --range-w-wick "$RANGE_W_WICK" \
        --range-w-mr "$RANGE_W_MR" \
        --range-w-bb-pos "$RANGE_W_BB_POS" \
        --range-w-vol "$RANGE_W_VOL" \
        --range-w-reversal-bonus "$RANGE_W_REVERSAL_BONUS" \
        --range-exit-atr-trail-multiplier "$RANGE_EXIT_ATR_TRAIL_MULTIPLIER" \
        ${DRIFT_REPORT_PATH:+--drift-report-path "$DRIFT_REPORT_PATH"} \
        ${ML_ARTIFACT_PATH:+--ml-artifact-path "$ML_ARTIFACT_PATH"} \
        ${ALLOWED_HOURS:+--allowed-hours "$ALLOWED_HOURS"}
    else
      "$PYTHON_BIN" -m auto_trader.strategy \
        --strategy "$strategy" \
        --features-path "$feature_path" \
        --regime-path "$regime_path" \
        --symbol "$symbol" \
        --timeframe "$timeframe" \
        --output-dir "$DATA_ROOT/signals" \
        --trend-min-entry-score "$TREND_MIN_ENTRY_SCORE" \
        --trend-breakout-persistence-min "$TREND_BREAKOUT_PERSISTENCE_MIN" \
        --trend-momentum-persistence-min "$TREND_MOMENTUM_PERSISTENCE_MIN" \
        --trend-pullback-shallowness-min "$TREND_PULLBACK_SHALLOWNESS_MIN" \
        --trend-higher-high-persistence-min "$TREND_HIGHER_HIGH_PERSISTENCE_MIN" \
        --trend-efficiency-exit-threshold "$TREND_EFFICIENCY_EXIT_THRESHOLD" \
        --trend-reentry-cooldown-bars "$TREND_REENTRY_COOLDOWN_BARS" \
        --trend-max-hold-bars "$TREND_MAX_HOLD_BARS" \
        --trend-enabled-symbols "$TREND_ENABLED_SYMBOLS" \
        ${DRIFT_REPORT_PATH:+--drift-report-path "$DRIFT_REPORT_PATH"} \
        ${ML_ARTIFACT_PATH:+--ml-artifact-path "$ML_ARTIFACT_PATH"} \
        ${ALLOWED_HOURS:+--allowed-hours "$ALLOWED_HOURS"}
    fi

    "$PYTHON_BIN" - "$DATA_ROOT/signals/${symbol}_${timeframe}_${strategy}_signals.parquet" <<'PY'
import sys
from pathlib import Path

p = Path(sys.argv[1])
if not p.exists():
    raise SystemExit(f"invalid signals parquet (missing): {p}")
size = p.stat().st_size
if size < 12:
    raise SystemExit(f"invalid signals parquet (too small={size}): {p}")
with p.open("rb") as f:
    head = f.read(4)
    f.seek(-4, 2)
    tail = f.read(4)
if head != b"PAR1" or tail != b"PAR1":
    raise SystemExit(f"invalid signals parquet (magic bytes mismatch): {p}")
PY

    "$PYTHON_BIN" -m auto_trader.analysis \
      --ohlcv-path "$target_ohlcv" \
      --signals-path "$DATA_ROOT/signals/${symbol}_${timeframe}_${strategy}_signals.parquet" \
      --symbol "$symbol" \
      --timeframe "$timeframe" \
      --strategy "$strategy" \
      --folds "$FOLDS" \
      --fee-rate "$FEE_RATE" \
      --slippage-rate "$SLIPPAGE_RATE" \
      --spread-rate "$SPREAD_RATE" \
      --delay-bars "$DELAY_BARS" \
      --order-mode "$ORDER_MODE" \
      --maker-fee-rate "$MAKER_FEE_RATE" \
      --taker-fee-rate "$TAKER_FEE_RATE" \
      --limit-offset-rate "$LIMIT_OFFSET_RATE" \
      --limit-partial-fill-ratio "$LIMIT_PARTIAL_FILL_RATIO" \
      --output-dir "$DATA_ROOT/analysis" >/dev/null
  done
  echo "[DONE] $symbol/$timeframe"
}

if (( PARALLEL <= 1 )); then
  for symbol in ${SYMBOLS//,/ }; do
    for timeframe in ${TIMEFRAMES//,/ }; do
      run_symbol_timeframe "$symbol" "$timeframe"
    done
  done
else
  pids=()
  labels=()
  for symbol in ${SYMBOLS//,/ }; do
    for timeframe in ${TIMEFRAMES//,/ }; do
      run_symbol_timeframe "$symbol" "$timeframe" &
      pids+=("$!")
      labels+=("$symbol/$timeframe")
      if (( ${#pids[@]} >= PARALLEL )); then
        if ! wait "${pids[0]}"; then
          echo "[FAILED] ${labels[0]}" >&2
          exit 1
        fi
        pids=("${pids[@]:1}")
        labels=("${labels[@]:1}")
      fi
    done
  done

  for i in "${!pids[@]}"; do
    if ! wait "${pids[$i]}"; then
      echo "[FAILED] ${labels[$i]}" >&2
      exit 1
    fi
  done
fi

"$PYTHON_BIN" - "$SYMBOLS" "$TIMEFRAMES" "$STRATEGIES" "$SUMMARY_PATH" "$FEE_RATE" "$SLIPPAGE_RATE" "$SPREAD_RATE" "$DELAY_BARS" "$DATA_ROOT" "$ORDER_MODE" "$MAKER_FEE_RATE" "$TAKER_FEE_RATE" "$LIMIT_OFFSET_RATE" "$LIMIT_PARTIAL_FILL_RATIO" <<'PY'
import json
import sys
from pathlib import Path
import pandas as pd

symbols = [x for x in sys.argv[1].split(",") if x]
timeframes = [x for x in sys.argv[2].split(",") if x]
strategies = [x for x in sys.argv[3].split(",") if x]
summary_path = Path(sys.argv[4])
data_root = Path(sys.argv[9])

rows = []
for symbol in symbols:
    for timeframe in timeframes:
        for strategy in strategies:
            p = data_root / "analysis" / f"walkforward_{symbol}_{timeframe}_{strategy}_summary.parquet"
            if not p.exists():
                continue
            df = pd.read_parquet(p)
            if df.empty:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "strategy": strategy,
                    "folds": int(len(df)),
                    "pf_mean": float(df["pf"].mean()),
                    "win_rate_mean": float(df["win_rate"].mean()),
                    "expectancy_mean": float(df["expectancy"].mean()),
                    "expectancy_bps_mean": float(df["expectancy_bps"].mean()),
                    "max_dd_mean": float(df["max_dd"].mean()),
                    "monthly_pnl_mean": float(df["monthly_pnl"].mean()),
                    "period_pnl_mean": float(df["period_pnl"].mean()),
                    "gross_pnl_est_mean": float(df["gross_pnl_est"].mean()),
                    "total_cost_est_mean": float(df["total_cost_est"].mean()),
                    "closed_trades_mean": float(df["closed_trades"].mean()),
                    "limit_order_count_mean": float(df["limit_order_count"].mean()),
                    "limit_filled_count_mean": float(df["limit_filled_count"].mean()),
                    "limit_partial_count_mean": float(df["limit_partial_count"].mean()),
                    "limit_expired_count_mean": float(df["limit_expired_count"].mean()),
                    "limit_canceled_count_mean": float(df["limit_canceled_count"].mean()),
                    "limit_fill_rate_mean": float(df["limit_fill_rate"].mean()),
                    "limit_maker_fill_rate_mean": float(df["limit_maker_fill_rate"].mean()),
                    "limit_taker_like_rate_mean": float(df["limit_taker_like_rate"].mean()),
                }
            )

if not rows:
    raise SystemExit("no walkforward summaries found")

table = pd.DataFrame(rows).sort_values(["strategy", "symbol", "timeframe"]).reset_index(drop=True)
best_rows = []
for (strategy, symbol), g in table.groupby(["strategy", "symbol"], sort=False):
    ranked = g.sort_values(
        ["expectancy_bps_mean", "pf_mean", "max_dd_mean", "period_pnl_mean"],
        ascending=[False, False, True, False],
    )
    best_rows.append(ranked.iloc[0].to_dict())

out = {
    "rows": rows,
    "best_by_symbol_strategy": best_rows,
    "config": {
        "fee_rate": float(sys.argv[5]),
        "slippage_rate": float(sys.argv[6]),
        "spread_rate": float(sys.argv[7]),
        "delay_bars": int(sys.argv[8]),
        "order_mode": str(sys.argv[10]),
        "maker_fee_rate": float(sys.argv[11]),
        "taker_fee_rate": float(sys.argv[12]),
        "limit_offset_rate": float(sys.argv[13]),
        "limit_partial_fill_ratio": float(sys.argv[14]),
    },
}
summary_path.write_text(json.dumps(out, ensure_ascii=True, indent=2), encoding="utf-8")
print(summary_path)
PY

if [[ -n "$CANDIDATE_REPORT_PATH" ]]; then
  "$PYTHON_BIN" - "$SUMMARY_PATH" "$CANDIDATE_REPORT_PATH" \
    "$CORE_MIN_PF" "$CORE_MIN_EXPECTANCY_BPS" "$CORE_MIN_PERIOD_PNL" "$CORE_MAX_DRAWDOWN" \
    "$PROBE_MIN_PF" "$PROBE_MIN_EXPECTANCY_BPS" "$PROBE_MIN_PERIOD_PNL" "$PROBE_MAX_DRAWDOWN" \
    "$MIN_CLOSED_TRADES" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

from auto_trader.analysis.candidates import CandidateThresholds, write_candidate_report

summary_path = Path(sys.argv[1])
candidate_path = Path(sys.argv[2])
thresholds = CandidateThresholds(
    core_min_pf=float(sys.argv[3]),
    core_min_expectancy_bps=float(sys.argv[4]),
    core_min_period_pnl=float(sys.argv[5]),
    core_max_drawdown=float(sys.argv[6]),
    probe_min_pf=float(sys.argv[7]),
    probe_min_expectancy_bps=float(sys.argv[8]),
    probe_min_period_pnl=float(sys.argv[9]),
    probe_max_drawdown=float(sys.argv[10]),
    min_closed_trades=float(sys.argv[11]),
)
report = write_candidate_report(summary_path, json_path=candidate_path, thresholds=thresholds)
print(candidate_path)
print(report["status"])
PY
fi

echo "done: $SUMMARY_PATH"
