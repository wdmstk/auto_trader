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
OUT_DIR="${OUT_DIR:-data/validation/core_expansion}"
PARALLEL="${PARALLEL:-4}"
CASE_PARALLEL="${CASE_PARALLEL:-2}"
HOLD_CASE_PARALLEL="${HOLD_CASE_PARALLEL:-$CASE_PARALLEL}"
REGIME_CASE_PARALLEL="${REGIME_CASE_PARALLEL:-$CASE_PARALLEL}"
OUTPUT_LAYOUT="${OUTPUT_LAYOUT:-legacy}"
BASELINE_DIR="${BASELINE_DIR:-$OUT_DIR/baseline_all_symbols}"
BASELINE_DATA_ROOT="${BASELINE_DATA_ROOT:-$BASELINE_DIR/run_data}"
BASELINE_SUMMARY_PATH="${BASELINE_SUMMARY_PATH:-$BASELINE_DIR/timeframe_comparison_summary.json}"
BASELINE_CANDIDATE_REPORT_PATH="${BASELINE_CANDIDATE_REPORT_PATH:-$BASELINE_DIR/candidate_report.json}"
BASELINE_RESULT_LIST_PATH="${BASELINE_RESULT_LIST_PATH:-$BASELINE_DIR/timeframe_comparison_result_list.md}"
if [[ "$OUTPUT_LAYOUT" == "simple_stage" ]]; then
  RANGE_MATRIX_DIR="$OUT_DIR/cases"
  RANGE_QUALITY_DIR="$OUT_DIR/cases"
  TREND_MATRIX_DIR="$OUT_DIR/cases"
  TREND_NEXT_STEP_DIR="$OUT_DIR/cases"
  TREND_PROVISIONAL_CORE_DIR="$OUT_DIR/cases"
  TREND_ENTRY_THRESHOLD_DIR="$OUT_DIR/cases"
  HOLD_EXIT_DIR="$OUT_DIR/cases"
  REGIME_THRESHOLD_DIR="$OUT_DIR/cases"
  RANGE_REGIME_THRESHOLD_DIR="$OUT_DIR/cases"
else
  RANGE_MATRIX_DIR="$OUT_DIR/range_matrix"
  RANGE_QUALITY_DIR="$OUT_DIR/range_quality_matrix"
  TREND_MATRIX_DIR="$OUT_DIR/trend_matrix"
  TREND_NEXT_STEP_DIR="$OUT_DIR/trend_next_step_matrix"
  TREND_PROVISIONAL_CORE_DIR="$OUT_DIR/trend_provisional_core_matrix"
  TREND_ENTRY_THRESHOLD_DIR="$OUT_DIR/trend_entry_threshold_matrix"
  HOLD_EXIT_DIR="$OUT_DIR/hold_exit_matrix"
  REGIME_THRESHOLD_DIR="$OUT_DIR/regime_threshold_matrix"
  RANGE_REGIME_THRESHOLD_DIR="$OUT_DIR/range_regime_threshold_matrix"
fi
AGGREGATE_JSON="$OUT_DIR/core_expansion_tuning_summary.json"
AGGREGATE_MD="$OUT_DIR/core_expansion_tuning_summary.md"
TREND_NEXT_STEP_JSON="$OUT_DIR/trend_next_step_summary.json"
TREND_NEXT_STEP_MD="$OUT_DIR/trend_next_step_summary.md"
TREND_PROVISIONAL_CORE_JSON="$OUT_DIR/trend_provisional_core_summary.json"
TREND_PROVISIONAL_CORE_MD="$OUT_DIR/trend_provisional_core_summary.md"
TREND_ENTRY_THRESHOLD_JSON="$OUT_DIR/trend_entry_threshold_summary.json"
TREND_ENTRY_THRESHOLD_MD="$OUT_DIR/trend_entry_threshold_summary.md"
HOLD_EXIT_JSON="$OUT_DIR/hold_exit_summary.json"
HOLD_EXIT_MD="$OUT_DIR/hold_exit_summary.md"
REGIME_THRESHOLD_JSON="$OUT_DIR/regime_threshold_summary.json"
REGIME_THRESHOLD_MD="$OUT_DIR/regime_threshold_summary.md"
RANGE_QUALITY_JSON="$OUT_DIR/range_quality_summary.json"
RANGE_QUALITY_MD="$OUT_DIR/range_quality_summary.md"
RANGE_REGIME_THRESHOLD_JSON="$OUT_DIR/range_regime_threshold_summary.json"
RANGE_REGIME_THRESHOLD_MD="$OUT_DIR/range_regime_threshold_summary.md"
TREND_ENTRY_DIAGNOSTICS_JSON="$OUT_DIR/trend_entry_diagnostics.json"
TREND_ENTRY_DIAGNOSTICS_MD="$OUT_DIR/trend_entry_diagnostics.md"
FOLD_BREAKDOWN_MD="$OUT_DIR/fold_breakdown.md"
LOSS_FOLD_REVIEW_JSON="$OUT_DIR/loss_fold_review.json"
LOSS_FOLD_REVIEW_MD="$OUT_DIR/loss_fold_review.md"
LOSS_FOLD_TRADE_DETAIL_JSON="$OUT_DIR/loss_fold_trade_detail.json"
LOSS_FOLD_TRADE_DETAIL_MD="$OUT_DIR/loss_fold_trade_detail.md"
LOSS_FOLD_TRADE_DETAIL_MAX_ROUTES="${LOSS_FOLD_TRADE_DETAIL_MAX_ROUTES:-10}"
LOSS_HOLD_THRESHOLD_JSON="$OUT_DIR/loss_hold_threshold.json"
LOSS_HOLD_THRESHOLD_MD="$OUT_DIR/loss_hold_threshold.md"

TUNING_PROFILE="${TUNING_PROFILE:-default}"
RUN_BASELINE="${RUN_BASELINE:-1}"
RUN_RANGE_MATRIX="${RUN_RANGE_MATRIX:-0}"
RUN_RANGE_QUALITY_MATRIX="${RUN_RANGE_QUALITY_MATRIX:-1}"
RUN_TREND_MATRIX="${RUN_TREND_MATRIX:-0}"
RUN_TREND_NEXT_STEP_MATRIX="${RUN_TREND_NEXT_STEP_MATRIX:-1}"
RUN_TREND_PROVISIONAL_CORE_MATRIX="${RUN_TREND_PROVISIONAL_CORE_MATRIX:-0}"
RUN_TREND_ENTRY_THRESHOLD_MATRIX="${RUN_TREND_ENTRY_THRESHOLD_MATRIX:-1}"
RUN_HOLD_EXIT_MATRIX="${RUN_HOLD_EXIT_MATRIX:-1}"
RUN_REGIME_THRESHOLD_MATRIX="${RUN_REGIME_THRESHOLD_MATRIX:-0}"
RUN_TREND_ENTRY_DIAGNOSTICS="${RUN_TREND_ENTRY_DIAGNOSTICS:-1}"
RUN_FOLD_BREAKDOWN="${RUN_FOLD_BREAKDOWN:-1}"
RUN_LOSS_FOLD_REVIEW="${RUN_LOSS_FOLD_REVIEW:-1}"
RUN_LOSS_FOLD_TRADE_DETAIL="${RUN_LOSS_FOLD_TRADE_DETAIL:-1}"
RUN_LOSS_HOLD_THRESHOLD="${RUN_LOSS_HOLD_THRESHOLD:-1}"
RUN_BUILD_AGGREGATE_REPORT="${RUN_BUILD_AGGREGATE_REPORT:-1}"
RUN_BUILD_TREND_NEXT_STEP_REPORT="${RUN_BUILD_TREND_NEXT_STEP_REPORT:-1}"
RUN_BUILD_TREND_PROVISIONAL_CORE_REPORT="${RUN_BUILD_TREND_PROVISIONAL_CORE_REPORT:-0}"
RUN_BUILD_TREND_ENTRY_THRESHOLD_REPORT="${RUN_BUILD_TREND_ENTRY_THRESHOLD_REPORT:-1}"
RUN_BUILD_HOLD_EXIT_REPORT="${RUN_BUILD_HOLD_EXIT_REPORT:-1}"
RUN_BUILD_REGIME_THRESHOLD_REPORT="${RUN_BUILD_REGIME_THRESHOLD_REPORT:-0}"
RUN_RANGE_REGIME_THRESHOLD_MATRIX="${RUN_RANGE_REGIME_THRESHOLD_MATRIX:-0}"
RUN_BUILD_RANGE_QUALITY_REPORT="${RUN_BUILD_RANGE_QUALITY_REPORT:-1}"
LOSS_HOLD_THRESHOLD_MAX_ROUTES="${LOSS_HOLD_THRESHOLD_MAX_ROUTES:-10}"
LOSS_HOLD_THRESHOLDS_HOURS="${LOSS_HOLD_THRESHOLDS_HOURS:-2,4,6,8,12,24,36,48}"

SYMBOLS_ALL="${SYMBOLS_ALL:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT,ADAUSDT}"
TIMEFRAMES_ALL="${TIMEFRAMES_ALL:-15m,30m,1h}"
STRATEGIES_ALL="${STRATEGIES_ALL:-range,trend}"

RANGE_TARGET_SYMBOLS="${RANGE_TARGET_SYMBOLS:-BTCUSDT,ETHUSDT}"
RANGE_TARGET_TIMEFRAME="${RANGE_TARGET_TIMEFRAME:-30m}"
RANGE_WICK_RATIO_MIN_LIST="${RANGE_WICK_RATIO_MIN_LIST:-0.2,0.15,0.1}"
RANGE_REQUIRE_REVERSAL_CANDLE_LIST="${RANGE_REQUIRE_REVERSAL_CANDLE_LIST:-false,true}"
RANGE_REENTRY_COOLDOWN_BARS_LIST="${RANGE_REENTRY_COOLDOWN_BARS_LIST:-2,1,0}"
RANGE_QUALITY_SYMBOLS="${RANGE_QUALITY_SYMBOLS:-BTCUSDT,ETHUSDT}"
RANGE_QUALITY_TIMEFRAMES="${RANGE_QUALITY_TIMEFRAMES:-15m,30m}"
RANGE_RSI_MIN_LIST="${RANGE_RSI_MIN_LIST:-35,40}"
RANGE_RSI_MAX_LIST="${RANGE_RSI_MAX_LIST:-50,55}"
RANGE_MR_DISTANCE_MAX_LIST="${RANGE_MR_DISTANCE_MAX_LIST:--0.3,-0.5,-0.1}"
RANGE_EXIT_NEUTRAL_ABS_LIST="${RANGE_EXIT_NEUTRAL_ABS_LIST:-0.1,0.15,0.2}"
RANGE_QUALITY_MIN_ENTRY_SCORE_LIST="${RANGE_QUALITY_MIN_ENTRY_SCORE_LIST:-0.5,0.6,0.75}"
RANGE_SR_SUPPORT_DISTANCE_MAX_LIST="${RANGE_SR_SUPPORT_DISTANCE_MAX_LIST:-1.0,1.5,2.0}"
RANGE_SR_MIN_LEVEL_STRENGTH_LIST="${RANGE_SR_MIN_LEVEL_STRENGTH_LIST:-1,2,3}"

TREND_TARGET_SYMBOLS="${TREND_TARGET_SYMBOLS:-ETHUSDT,ADAUSDT}"
TREND_TARGET_TIMEFRAMES="${TREND_TARGET_TIMEFRAMES:-15m,1h}"
TREND_REENTRY_COOLDOWN_BARS_LIST="${TREND_REENTRY_COOLDOWN_BARS_LIST:-2,1,0}"
TREND_NEXT_STEP_SYMBOLS="${TREND_NEXT_STEP_SYMBOLS:-ETHUSDT,XRPUSDT}"
TREND_NEXT_STEP_TIMEFRAMES="${TREND_NEXT_STEP_TIMEFRAMES:-15m,1h}"
TREND_NEXT_STEP_ROUTES="${TREND_NEXT_STEP_ROUTES:-trend:ETHUSDT:15m,trend:XRPUSDT:1h}"
TREND_EFFICIENCY_EXIT_THRESHOLD_LIST="${TREND_EFFICIENCY_EXIT_THRESHOLD_LIST:-0.1,0.08,0.05,0.02}"
TREND_PROVISIONAL_CORE_SYMBOLS="${TREND_PROVISIONAL_CORE_SYMBOLS:-ETHUSDT,XRPUSDT}"
TREND_PROVISIONAL_CORE_TIMEFRAMES="${TREND_PROVISIONAL_CORE_TIMEFRAMES:-1h}"
TREND_PROVISIONAL_CORE_ROUTES="${TREND_PROVISIONAL_CORE_ROUTES:-trend:ETHUSDT:1h,trend:XRPUSDT:1h}"
TREND_PROVISIONAL_CORE_COOLDOWN_LIST="${TREND_PROVISIONAL_CORE_COOLDOWN_LIST:-1,2}"
TREND_PROVISIONAL_CORE_EXIT_THRESHOLD_LIST="${TREND_PROVISIONAL_CORE_EXIT_THRESHOLD_LIST:-0.02,0.05,0.1}"
TREND_PROVISIONAL_CORE_MIN_ENTRY_SCORE_LIST="${TREND_PROVISIONAL_CORE_MIN_ENTRY_SCORE_LIST:-1.0,0.75,0.5}"
TREND_ENTRY_THRESHOLD_SYMBOLS="${TREND_ENTRY_THRESHOLD_SYMBOLS:-ETHUSDT,ADAUSDT,XRPUSDT}"
TREND_ENTRY_THRESHOLD_TIMEFRAMES="${TREND_ENTRY_THRESHOLD_TIMEFRAMES:-15m,1h}"
TREND_ENTRY_THRESHOLD_ROUTES="${TREND_ENTRY_THRESHOLD_ROUTES:-trend:ETHUSDT:15m,trend:ADAUSDT:1h,trend:ETHUSDT:1h,trend:XRPUSDT:1h}"
TREND_ENTRY_THRESHOLD_COOLDOWN_LIST="${TREND_ENTRY_THRESHOLD_COOLDOWN_LIST:-1,2}"
TREND_ENTRY_THRESHOLD_EXIT_THRESHOLD_LIST="${TREND_ENTRY_THRESHOLD_EXIT_THRESHOLD_LIST:-0.1,0.02}"
TREND_BREAKOUT_PERSISTENCE_MIN_LIST="${TREND_BREAKOUT_PERSISTENCE_MIN_LIST:-0.6,0.55,0.5}"
TREND_MOMENTUM_PERSISTENCE_MIN_LIST="${TREND_MOMENTUM_PERSISTENCE_MIN_LIST:-0.5,0.45,0.4}"
TREND_PULLBACK_SHALLOWNESS_MIN_LIST="${TREND_PULLBACK_SHALLOWNESS_MIN_LIST:-0.5}"
TREND_HIGHER_HIGH_PERSISTENCE_MIN_LIST="${TREND_HIGHER_HIGH_PERSISTENCE_MIN_LIST:-0.5,0.45,0.4}"
TREND_DIAGNOSTIC_ROUTES="${TREND_DIAGNOSTIC_ROUTES:-trend:ETHUSDT:15m,trend:ADAUSDT:1h,trend:ETHUSDT:1h,trend:XRPUSDT:1h}"
HOLD_EXIT_ROUTES="${HOLD_EXIT_ROUTES:-range:ETHUSDT:15m,trend:ETHUSDT:1h,range:XRPUSDT:1h}"
HOLD_EXIT_RANGE_SYMBOLS="${HOLD_EXIT_RANGE_SYMBOLS-ETHUSDT,XRPUSDT}"
HOLD_EXIT_RANGE_TIMEFRAMES="${HOLD_EXIT_RANGE_TIMEFRAMES-15m,1h}"
HOLD_EXIT_TREND_SYMBOLS="${HOLD_EXIT_TREND_SYMBOLS-ETHUSDT}"
HOLD_EXIT_TREND_TIMEFRAMES="${HOLD_EXIT_TREND_TIMEFRAMES-1h}"
RANGE_MAX_HOLD_BARS_LIST="${RANGE_MAX_HOLD_BARS_LIST-0,8,16,24,32}"
TREND_MAX_HOLD_BARS_LIST="${TREND_MAX_HOLD_BARS_LIST-0,2,4,6,8}"
REGIME_THRESHOLD_ROUTES="${REGIME_THRESHOLD_ROUTES:-trend:BTCUSDT:1h}"
REGIME_THRESHOLD_SYMBOLS="${REGIME_THRESHOLD_SYMBOLS:-BTCUSDT}"
REGIME_THRESHOLD_TIMEFRAMES="${REGIME_THRESHOLD_TIMEFRAMES:-1h}"
REGIME_TREND_ADX_THRESHOLD_LIST="${REGIME_TREND_ADX_THRESHOLD_LIST:-25,22,20,18}"
REGIME_TREND_BREAKOUT_PERSISTENCE_MIN_BARS_LIST="${REGIME_TREND_BREAKOUT_PERSISTENCE_MIN_BARS_LIST:-3,2}"
MIN_REGIME_HOLD_BARS_LIST="${MIN_REGIME_HOLD_BARS_LIST:-3,2,1}"
HIGH_VOL_COOLDOWN_BARS_LIST="${HIGH_VOL_COOLDOWN_BARS_LIST:-5,3,1}"
REGIME_RANGE_SYMBOLS="${REGIME_RANGE_SYMBOLS:-BTCUSDT,ETHUSDT}"
REGIME_RANGE_TIMEFRAMES="${REGIME_RANGE_TIMEFRAMES:-15m,30m}"
REGIME_RANGE_BB_WIDTH_PERCENTILE_MAX_LIST="${REGIME_RANGE_BB_WIDTH_PERCENTILE_MAX_LIST:-40,50,60}"
REGIME_RANGE_ADX_MAX_LIST="${REGIME_RANGE_ADX_MAX_LIST:-20,25,30}"

CORE_CANDIDATE_ROUTES="${CORE_CANDIDATE_ROUTES:-range:SOLUSDT:30m,trend:ETHUSDT:15m,trend:ADAUSDT:1h,trend:ETHUSDT:1h,range:XRPUSDT:30m}"
LOGIC_REVIEW_ROUTES="${LOGIC_REVIEW_ROUTES:-range:BNBUSDT:30m,range:ADAUSDT:15m,range:SOLUSDT:30m,trend:XRPUSDT:1h,trend:ETHUSDT:15m}"

FEE_RATE="${FEE_RATE:-0.0002}"
SLIPPAGE_RATE="${SLIPPAGE_RATE:-0.0002}"
SPREAD_RATE="${SPREAD_RATE:-0.0001}"
DELAY_BARS="${DELAY_BARS:-1}"

mkdir -p "$OUT_DIR"

apply_profile_defaults() {
  case "$TUNING_PROFILE" in
    default)
      ;;
    hold_only)
      RUN_RANGE_MATRIX=0
      RUN_RANGE_QUALITY_MATRIX=0
      RUN_RANGE_REGIME_THRESHOLD_MATRIX=0
      RUN_TREND_MATRIX=0
      RUN_TREND_NEXT_STEP_MATRIX=0
      RUN_TREND_PROVISIONAL_CORE_MATRIX=0
      RUN_TREND_ENTRY_THRESHOLD_MATRIX=0
      RUN_HOLD_EXIT_MATRIX=1
      RUN_REGIME_THRESHOLD_MATRIX=0
      RUN_TREND_ENTRY_DIAGNOSTICS=0
      RUN_FOLD_BREAKDOWN=0
      RUN_LOSS_FOLD_REVIEW=0
      RUN_LOSS_FOLD_TRADE_DETAIL=0
      RUN_LOSS_HOLD_THRESHOLD=1
      RUN_BUILD_AGGREGATE_REPORT=0
      RUN_BUILD_TREND_NEXT_STEP_REPORT=0
      RUN_BUILD_TREND_PROVISIONAL_CORE_REPORT=0
      RUN_BUILD_TREND_ENTRY_THRESHOLD_REPORT=0
      RUN_BUILD_HOLD_EXIT_REPORT=1
      RUN_BUILD_REGIME_THRESHOLD_REPORT=0
      ;;
    hold_fine)
      RUN_RANGE_MATRIX=0
      RUN_RANGE_QUALITY_MATRIX=0
      RUN_RANGE_REGIME_THRESHOLD_MATRIX=0
      RUN_TREND_MATRIX=0
      RUN_TREND_NEXT_STEP_MATRIX=0
      RUN_TREND_PROVISIONAL_CORE_MATRIX=0
      RUN_TREND_ENTRY_THRESHOLD_MATRIX=0
      RUN_HOLD_EXIT_MATRIX=1
      RUN_REGIME_THRESHOLD_MATRIX=0
      RUN_TREND_ENTRY_DIAGNOSTICS=0
      RUN_FOLD_BREAKDOWN=0
      RUN_LOSS_FOLD_REVIEW=0
      RUN_LOSS_FOLD_TRADE_DETAIL=0
      RUN_LOSS_HOLD_THRESHOLD=1
      RUN_BUILD_AGGREGATE_REPORT=0
      RUN_BUILD_TREND_NEXT_STEP_REPORT=0
      RUN_BUILD_TREND_PROVISIONAL_CORE_REPORT=0
      RUN_BUILD_TREND_ENTRY_THRESHOLD_REPORT=0
      RUN_BUILD_HOLD_EXIT_REPORT=1
      RUN_BUILD_REGIME_THRESHOLD_REPORT=0
      HOLD_EXIT_ROUTES="range:ETHUSDT:15m,trend:ETHUSDT:1h,range:XRPUSDT:1h"
      HOLD_EXIT_RANGE_SYMBOLS="ETHUSDT,XRPUSDT"
      HOLD_EXIT_RANGE_TIMEFRAMES="15m,1h"
      HOLD_EXIT_TREND_SYMBOLS="ETHUSDT"
      HOLD_EXIT_TREND_TIMEFRAMES="1h"
      RANGE_MAX_HOLD_BARS_LIST="20,24,28"
      TREND_MAX_HOLD_BARS_LIST="3,4,5,6"
      LOSS_HOLD_THRESHOLD_MAX_ROUTES=3
      ;;
    regime_only)
      RUN_BASELINE=1
      RUN_RANGE_MATRIX=0
      RUN_RANGE_QUALITY_MATRIX=0
      RUN_RANGE_REGIME_THRESHOLD_MATRIX=0
      RUN_TREND_MATRIX=0
      RUN_TREND_NEXT_STEP_MATRIX=0
      RUN_TREND_PROVISIONAL_CORE_MATRIX=0
      RUN_TREND_ENTRY_THRESHOLD_MATRIX=0
      RUN_HOLD_EXIT_MATRIX=0
      RUN_REGIME_THRESHOLD_MATRIX=1
      RUN_TREND_ENTRY_DIAGNOSTICS=0
      RUN_FOLD_BREAKDOWN=0
      RUN_LOSS_FOLD_REVIEW=0
      RUN_LOSS_FOLD_TRADE_DETAIL=0
      RUN_LOSS_HOLD_THRESHOLD=0
      RUN_BUILD_AGGREGATE_REPORT=0
      RUN_BUILD_TREND_NEXT_STEP_REPORT=0
      RUN_BUILD_TREND_PROVISIONAL_CORE_REPORT=0
      RUN_BUILD_TREND_ENTRY_THRESHOLD_REPORT=0
      RUN_BUILD_HOLD_EXIT_REPORT=0
      RUN_BUILD_REGIME_THRESHOLD_REPORT=1
      ;;
    *)
      echo "unsupported TUNING_PROFILE: $TUNING_PROFILE" >&2
      exit 1
      ;;
  esac
}

apply_profile_defaults

echo "== core expansion tuning =="
echo "out_dir=$OUT_DIR"
echo "baseline_dir=$BASELINE_DIR"
echo "parallel=$PARALLEL case_parallel=$CASE_PARALLEL hold_case_parallel=$HOLD_CASE_PARALLEL regime_case_parallel=$REGIME_CASE_PARALLEL"
echo "output_layout=$OUTPUT_LAYOUT"
echo "tuning_profile=$TUNING_PROFILE"
echo "run_flags: baseline=$RUN_BASELINE range_matrix=$RUN_RANGE_MATRIX range_quality=$RUN_RANGE_QUALITY_MATRIX range_regime=$RUN_RANGE_REGIME_THRESHOLD_MATRIX trend_matrix=$RUN_TREND_MATRIX trend_next=$RUN_TREND_NEXT_STEP_MATRIX trend_provisional=$RUN_TREND_PROVISIONAL_CORE_MATRIX trend_entry_threshold=$RUN_TREND_ENTRY_THRESHOLD_MATRIX hold_exit=$RUN_HOLD_EXIT_MATRIX regime_threshold=$RUN_REGIME_THRESHOLD_MATRIX"
echo "report_flags: diagnostics=$RUN_TREND_ENTRY_DIAGNOSTICS fold_breakdown=$RUN_FOLD_BREAKDOWN loss_fold_review=$RUN_LOSS_FOLD_REVIEW loss_fold_trade_detail=$RUN_LOSS_FOLD_TRADE_DETAIL loss_hold_threshold=$RUN_LOSS_HOLD_THRESHOLD aggregate=$RUN_BUILD_AGGREGATE_REPORT trend_next=$RUN_BUILD_TREND_NEXT_STEP_REPORT trend_provisional=$RUN_BUILD_TREND_PROVISIONAL_CORE_REPORT trend_entry_threshold=$RUN_BUILD_TREND_ENTRY_THRESHOLD_REPORT hold_exit=$RUN_BUILD_HOLD_EXIT_REPORT regime_threshold=$RUN_BUILD_REGIME_THRESHOLD_REPORT range_quality=$RUN_BUILD_RANGE_QUALITY_REPORT"

wait_for_slot() {
  local -n pids_ref=$1
  local -n labels_ref=$2
  if (( ${#pids_ref[@]} == 0 )); then
    return 0
  fi
  if ! wait "${pids_ref[0]}"; then
    echo "[FAILED] ${labels_ref[0]}" >&2
    exit 1
  fi
  pids_ref=("${pids_ref[@]:1}")
  labels_ref=("${labels_ref[@]:1}")
}

run_baseline() {
  SUMMARY_PATH="$BASELINE_SUMMARY_PATH" \
  CANDIDATE_REPORT_PATH="$BASELINE_CANDIDATE_REPORT_PATH" \
  OUT_DIR="$BASELINE_DIR" \
  DATA_ROOT="$BASELINE_DATA_ROOT" \
  BASE_DATA_ROOT=data \
  SYMBOLS="$SYMBOLS_ALL" \
  TIMEFRAMES="$TIMEFRAMES_ALL" \
  STRATEGIES="$STRATEGIES_ALL" \
  RANGE_ENABLED_SYMBOLS= \
  TREND_ENABLED_SYMBOLS= \
  RANGE_REQUIRE_REVERSAL_CANDLE=false \
  RANGE_WICK_RATIO_MIN=0.2 \
  RANGE_REENTRY_COOLDOWN_BARS=2 \
  TREND_REENTRY_COOLDOWN_BARS=2 \
  FEE_RATE="$FEE_RATE" \
  SLIPPAGE_RATE="$SLIPPAGE_RATE" \
  SPREAD_RATE="$SPREAD_RATE" \
  DELAY_BARS="$DELAY_BARS" \
  PARALLEL="$PARALLEL" \
  ./scripts/timeframe_comparison.sh

  SUMMARY_PATH="$BASELINE_SUMMARY_PATH" \
  CANDIDATE_REPORT_PATH="$BASELINE_CANDIDATE_REPORT_PATH" \
  OUT_PATH="$BASELINE_RESULT_LIST_PATH" \
  DATA_ROOT="$BASELINE_DATA_ROOT" \
  ./scripts/timeframe_comparison_results_list.sh
}

run_range_matrix() {
  local wick reversal cooldown label out_dir data_root
  local -a pids=()
  local -a labels=()
  for wick in ${RANGE_WICK_RATIO_MIN_LIST//,/ }; do
    for reversal in ${RANGE_REQUIRE_REVERSAL_CANDLE_LIST//,/ }; do
      for cooldown in ${RANGE_REENTRY_COOLDOWN_BARS_LIST//,/ }; do
        label="wick${wick}_reversal${reversal}_cooldown${cooldown}"
        out_dir="$RANGE_MATRIX_DIR/$label"
        data_root="$out_dir/run_data"
        (
          SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
          CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
          OUT_DIR="$out_dir" \
          DATA_ROOT="$data_root" \
          BASE_DATA_ROOT=data \
          SYMBOLS="$RANGE_TARGET_SYMBOLS" \
          TIMEFRAMES="$RANGE_TARGET_TIMEFRAME" \
          STRATEGIES=range \
          RANGE_ENABLED_SYMBOLS= \
          TREND_ENABLED_SYMBOLS= \
          RANGE_REQUIRE_REVERSAL_CANDLE="$reversal" \
          RANGE_WICK_RATIO_MIN="$wick" \
          RANGE_REENTRY_COOLDOWN_BARS="$cooldown" \
          FEE_RATE="$FEE_RATE" \
          SLIPPAGE_RATE="$SLIPPAGE_RATE" \
          SPREAD_RATE="$SPREAD_RATE" \
          DELAY_BARS="$DELAY_BARS" \
          PARALLEL="$PARALLEL" \
          ./scripts/timeframe_comparison.sh

          SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
          CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
          OUT_PATH="$out_dir/timeframe_comparison_result_list.md" \
          DATA_ROOT="$data_root" \
          ./scripts/timeframe_comparison_results_list.sh
        ) &
        pids+=("$!")
        labels+=("range/$label")
        if (( ${#pids[@]} >= CASE_PARALLEL )); then
          wait_for_slot pids labels
        fi
      done
    done
  done
  while (( ${#pids[@]} > 0 )); do
    wait_for_slot pids labels
  done
}

run_range_quality_matrix() {
  local rsi_min rsi_max mr_dist exit_neutral entry_score sr_dist sr_str label out_dir data_root
  local -a pids=()
  local -a labels=()
  for rsi_min in ${RANGE_RSI_MIN_LIST//,/ }; do
    for rsi_max in ${RANGE_RSI_MAX_LIST//,/ }; do
      for sr_dist in ${RANGE_SR_SUPPORT_DISTANCE_MAX_LIST//,/ }; do
        for sr_str in ${RANGE_SR_MIN_LEVEL_STRENGTH_LIST//,/ }; do
          for entry_score in ${RANGE_QUALITY_MIN_ENTRY_SCORE_LIST//,/ }; do
            label="rsi${rsi_min}-${rsi_max}_srd${sr_dist}_srs${sr_str}_score${entry_score}"
            out_dir="$RANGE_QUALITY_DIR/$label"
            data_root="$out_dir/run_data"
            (
              SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
              CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
              OUT_DIR="$out_dir" \
              DATA_ROOT="$data_root" \
              BASE_DATA_ROOT=data \
              SYMBOLS="$RANGE_QUALITY_SYMBOLS" \
              TIMEFRAMES="$RANGE_QUALITY_TIMEFRAMES" \
              STRATEGIES=range \
              RANGE_ENABLED_SYMBOLS= \
              TREND_ENABLED_SYMBOLS= \
              RANGE_RSI_MIN="$rsi_min" \
              RANGE_RSI_MAX="$rsi_max" \
              RANGE_MEAN_REVERSION_DISTANCE_MAX="${RANGE_MEAN_REVERSION_DISTANCE_MAX:--0.3}" \
              RANGE_EXIT_MEAN_REVERSION_NEUTRAL_ABS="${RANGE_EXIT_MEAN_REVERSION_NEUTRAL_ABS:-0.15}" \
              RANGE_MIN_ENTRY_SCORE="$entry_score" \
              RANGE_WICK_RATIO_MIN=0.3 \
              RANGE_REQUIRE_REVERSAL_CANDLE=false \
              RANGE_REENTRY_COOLDOWN_BARS=2 \
              RANGE_MAX_HOLD_BARS=16 \
              RANGE_BB_POSITION_MAX="${RANGE_BB_POSITION_MAX:-0.35}" \
              RANGE_VOLUME_SPIKE_THRESHOLD="${RANGE_VOLUME_SPIKE_THRESHOLD:-1.3}" \
              RANGE_PRICE_VS_RECENT_LOW_MAX="${RANGE_PRICE_VS_RECENT_LOW_MAX:-1.5}" \
              RANGE_W_RSI="${RANGE_W_RSI:-1.0}" \
              RANGE_W_WICK="${RANGE_W_WICK:-1.0}" \
              RANGE_W_MR="${RANGE_W_MR:-1.5}" \
              RANGE_W_BB_POS="${RANGE_W_BB_POS:-2.0}" \
              RANGE_W_VOL="${RANGE_W_VOL:-1.0}" \
              RANGE_W_REVERSAL_BONUS="${RANGE_W_REVERSAL_BONUS:-0.5}" \
              RANGE_EXIT_ATR_TRAIL_MULTIPLIER="${RANGE_EXIT_ATR_TRAIL_MULTIPLIER:-2.0}" \
              RANGE_SR_SUPPORT_DISTANCE_MAX="$sr_dist" \
              RANGE_SR_MIN_LEVEL_STRENGTH="$sr_str" \
              RANGE_SR_RESISTANCE_EXIT_ATR="${RANGE_SR_RESISTANCE_EXIT_ATR:-0.5}" \
              RANGE_W_SR_PROXIMITY="${RANGE_W_SR_PROXIMITY:-2.0}" \
              RANGE_W_SR_STRENGTH="${RANGE_W_SR_STRENGTH:-1.5}" \
              RANGE_SR_HTF_TIMEFRAME="${RANGE_SR_HTF_TIMEFRAME:-4h}" \
              SKIP_FEATURE_CACHE="${SKIP_FEATURE_CACHE:-0}" \
              FEE_RATE="$FEE_RATE" \
              SLIPPAGE_RATE="$SLIPPAGE_RATE" \
              SPREAD_RATE="$SPREAD_RATE" \
              DELAY_BARS="$DELAY_BARS" \
              PARALLEL="$PARALLEL" \
              ./scripts/timeframe_comparison.sh

              SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
              CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
              OUT_PATH="$out_dir/timeframe_comparison_result_list.md" \
              DATA_ROOT="$data_root" \
              ./scripts/timeframe_comparison_results_list.sh
            ) &
            pids+=("$!")
            labels+=("range-quality/$label")
            if (( ${#pids[@]} >= CASE_PARALLEL )); then
              wait_for_slot pids labels
            fi
          done
        done
      done
    done
  done
  while (( ${#pids[@]} > 0 )); do
    wait_for_slot pids labels
  done
}

run_range_regime_threshold_matrix() {
  local bb_width adx_max label out_dir data_root
  local -a pids=()
  local -a labels=()
  for bb_width in ${REGIME_RANGE_BB_WIDTH_PERCENTILE_MAX_LIST//,/ }; do
    for adx_max in ${REGIME_RANGE_ADX_MAX_LIST//,/ }; do
      label="bb_width${bb_width}_adx${adx_max}"
      out_dir="$RANGE_REGIME_THRESHOLD_DIR/$label"
      data_root="$out_dir/run_data"
      (
        SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
        CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
        OUT_DIR="$out_dir" \
        DATA_ROOT="$data_root" \
        BASE_DATA_ROOT=data \
        SYMBOLS="$REGIME_RANGE_SYMBOLS" \
        TIMEFRAMES="$REGIME_RANGE_TIMEFRAMES" \
        STRATEGIES=range \
        RANGE_ENABLED_SYMBOLS= \
        TREND_ENABLED_SYMBOLS= \
        RANGE_RSI_MIN=35 \
        RANGE_RSI_MAX=50 \
        RANGE_MEAN_REVERSION_DISTANCE_MAX=-0.3 \
        RANGE_EXIT_MEAN_REVERSION_NEUTRAL_ABS=0.15 \
        RANGE_MIN_ENTRY_SCORE=0.75 \
        RANGE_WICK_RATIO_MIN=0.3 \
        RANGE_REQUIRE_REVERSAL_CANDLE=false \
        RANGE_REENTRY_COOLDOWN_BARS=2 \
        RANGE_MAX_HOLD_BARS=16 \
        RANGE_BB_POSITION_MAX="${RANGE_BB_POSITION_MAX:-0.35}" \
        RANGE_VOLUME_SPIKE_THRESHOLD="${RANGE_VOLUME_SPIKE_THRESHOLD:-1.3}" \
        RANGE_PRICE_VS_RECENT_LOW_MAX="${RANGE_PRICE_VS_RECENT_LOW_MAX:-1.5}" \
        RANGE_W_RSI="${RANGE_W_RSI:-1.0}" \
        RANGE_W_WICK="${RANGE_W_WICK:-1.0}" \
        RANGE_W_MR="${RANGE_W_MR:-1.5}" \
        RANGE_W_BB_POS="${RANGE_W_BB_POS:-2.0}" \
        RANGE_W_VOL="${RANGE_W_VOL:-1.0}" \
        RANGE_W_REVERSAL_BONUS="${RANGE_W_REVERSAL_BONUS:-0.5}" \
        RANGE_EXIT_ATR_TRAIL_MULTIPLIER="${RANGE_EXIT_ATR_TRAIL_MULTIPLIER:-2.0}" \
        SKIP_FEATURE_CACHE="${SKIP_FEATURE_CACHE:-0}" \
        REGIME_RANGE_BB_WIDTH_PERCENTILE_MAX="$bb_width" \
        REGIME_RANGE_ADX_MAX="$adx_max" \
        FEE_RATE="$FEE_RATE" \
        SLIPPAGE_RATE="$SLIPPAGE_RATE" \
        SPREAD_RATE="$SPREAD_RATE" \
        DELAY_BARS="$DELAY_BARS" \
        PARALLEL="$PARALLEL" \
        ./scripts/timeframe_comparison.sh

        SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
        CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
        OUT_PATH="$out_dir/timeframe_comparison_result_list.md" \
        DATA_ROOT="$data_root" \
        ./scripts/timeframe_comparison_results_list.sh
      ) &
      pids+=("$!")
      labels+=("range-regime/$label")
      if (( ${#pids[@]} >= REGIME_CASE_PARALLEL )); then
        wait_for_slot pids labels
      fi
    done
  done
  while (( ${#pids[@]} > 0 )); do
    wait_for_slot pids labels
  done
}

run_trend_matrix() {
  local cooldown label out_dir data_root
  local -a pids=()
  local -a labels=()
  for cooldown in ${TREND_REENTRY_COOLDOWN_BARS_LIST//,/ }; do
    label="cooldown${cooldown}"
    out_dir="$TREND_MATRIX_DIR/$label"
    data_root="$out_dir/run_data"
    (
      SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
      CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
      OUT_DIR="$out_dir" \
      DATA_ROOT="$data_root" \
      BASE_DATA_ROOT=data \
      SYMBOLS="$TREND_TARGET_SYMBOLS" \
      TIMEFRAMES="$TREND_TARGET_TIMEFRAMES" \
      STRATEGIES=trend \
      RANGE_ENABLED_SYMBOLS= \
      TREND_ENABLED_SYMBOLS= \
      TREND_REENTRY_COOLDOWN_BARS="$cooldown" \
      FEE_RATE="$FEE_RATE" \
      SLIPPAGE_RATE="$SLIPPAGE_RATE" \
      SPREAD_RATE="$SPREAD_RATE" \
      DELAY_BARS="$DELAY_BARS" \
      PARALLEL="$PARALLEL" \
      ./scripts/timeframe_comparison.sh

      SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
      CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
      OUT_PATH="$out_dir/timeframe_comparison_result_list.md" \
      DATA_ROOT="$data_root" \
      ./scripts/timeframe_comparison_results_list.sh
    ) &
    pids+=("$!")
    labels+=("trend/$label")
    if (( ${#pids[@]} >= HOLD_CASE_PARALLEL )); then
      wait_for_slot pids labels
    fi
  done
  while (( ${#pids[@]} > 0 )); do
    wait_for_slot pids labels
  done
}

run_trend_next_step_matrix() {
  local cooldown exit_threshold label out_dir data_root
  local -a pids=()
  local -a labels=()
  for cooldown in ${TREND_REENTRY_COOLDOWN_BARS_LIST//,/ }; do
    for exit_threshold in ${TREND_EFFICIENCY_EXIT_THRESHOLD_LIST//,/ }; do
      label="cooldown${cooldown}_exit${exit_threshold}"
      out_dir="$TREND_NEXT_STEP_DIR/$label"
      data_root="$out_dir/run_data"
      (
        SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
        CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
        OUT_DIR="$out_dir" \
        DATA_ROOT="$data_root" \
        BASE_DATA_ROOT=data \
        SYMBOLS="$TREND_NEXT_STEP_SYMBOLS" \
        TIMEFRAMES="$TREND_NEXT_STEP_TIMEFRAMES" \
        STRATEGIES=trend \
        RANGE_ENABLED_SYMBOLS= \
        TREND_ENABLED_SYMBOLS= \
        TREND_EFFICIENCY_EXIT_THRESHOLD="$exit_threshold" \
        TREND_REENTRY_COOLDOWN_BARS="$cooldown" \
        FEE_RATE="$FEE_RATE" \
        SLIPPAGE_RATE="$SLIPPAGE_RATE" \
        SPREAD_RATE="$SPREAD_RATE" \
        DELAY_BARS="$DELAY_BARS" \
        PARALLEL="$PARALLEL" \
        ./scripts/timeframe_comparison.sh

        SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
        CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
        OUT_PATH="$out_dir/timeframe_comparison_result_list.md" \
        DATA_ROOT="$data_root" \
        ./scripts/timeframe_comparison_results_list.sh
      ) &
      pids+=("$!")
      labels+=("trend-next/$label")
      if (( ${#pids[@]} >= CASE_PARALLEL )); then
        wait_for_slot pids labels
      fi
    done
  done
  while (( ${#pids[@]} > 0 )); do
    wait_for_slot pids labels
  done
}

run_trend_provisional_core_matrix() {
  local cooldown exit_threshold min_score label out_dir data_root
  local -a pids=()
  local -a labels=()
  for cooldown in ${TREND_PROVISIONAL_CORE_COOLDOWN_LIST//,/ }; do
    for exit_threshold in ${TREND_PROVISIONAL_CORE_EXIT_THRESHOLD_LIST//,/ }; do
      for min_score in ${TREND_PROVISIONAL_CORE_MIN_ENTRY_SCORE_LIST//,/ }; do
        label="cooldown${cooldown}_exit${exit_threshold}_score${min_score}"
        out_dir="$TREND_PROVISIONAL_CORE_DIR/$label"
        data_root="$out_dir/run_data"
        (
          SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
          CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
          OUT_DIR="$out_dir" \
          DATA_ROOT="$data_root" \
          BASE_DATA_ROOT=data \
          SYMBOLS="$TREND_PROVISIONAL_CORE_SYMBOLS" \
          TIMEFRAMES="$TREND_PROVISIONAL_CORE_TIMEFRAMES" \
          STRATEGIES=trend \
          RANGE_ENABLED_SYMBOLS= \
          TREND_ENABLED_SYMBOLS= \
          TREND_MIN_ENTRY_SCORE="$min_score" \
          TREND_EFFICIENCY_EXIT_THRESHOLD="$exit_threshold" \
          TREND_REENTRY_COOLDOWN_BARS="$cooldown" \
          FEE_RATE="$FEE_RATE" \
          SLIPPAGE_RATE="$SLIPPAGE_RATE" \
          SPREAD_RATE="$SPREAD_RATE" \
          DELAY_BARS="$DELAY_BARS" \
          PARALLEL="$PARALLEL" \
          ./scripts/timeframe_comparison.sh

          SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
          CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
          OUT_PATH="$out_dir/timeframe_comparison_result_list.md" \
          DATA_ROOT="$data_root" \
          ./scripts/timeframe_comparison_results_list.sh
        ) &
        pids+=("$!")
        labels+=("trend-provisional/$label")
        if (( ${#pids[@]} >= CASE_PARALLEL )); then
          wait_for_slot pids labels
        fi
      done
    done
  done
  while (( ${#pids[@]} > 0 )); do
    wait_for_slot pids labels
  done
}

run_trend_entry_threshold_matrix() {
  local cooldown exit_threshold breakout momentum pullback higher_high label out_dir data_root
  local -a pids=()
  local -a labels=()
  for cooldown in ${TREND_ENTRY_THRESHOLD_COOLDOWN_LIST//,/ }; do
    for exit_threshold in ${TREND_ENTRY_THRESHOLD_EXIT_THRESHOLD_LIST//,/ }; do
      for breakout in ${TREND_BREAKOUT_PERSISTENCE_MIN_LIST//,/ }; do
        for momentum in ${TREND_MOMENTUM_PERSISTENCE_MIN_LIST//,/ }; do
          for pullback in ${TREND_PULLBACK_SHALLOWNESS_MIN_LIST//,/ }; do
            for higher_high in ${TREND_HIGHER_HIGH_PERSISTENCE_MIN_LIST//,/ }; do
              label="cooldown${cooldown}_exit${exit_threshold}_breakout${breakout}_momentum${momentum}_pullback${pullback}_higherhigh${higher_high}"
              out_dir="$TREND_ENTRY_THRESHOLD_DIR/$label"
              data_root="$out_dir/run_data"
              (
                SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
                CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
                OUT_DIR="$out_dir" \
                DATA_ROOT="$data_root" \
                BASE_DATA_ROOT=data \
                SYMBOLS="$TREND_ENTRY_THRESHOLD_SYMBOLS" \
                TIMEFRAMES="$TREND_ENTRY_THRESHOLD_TIMEFRAMES" \
                STRATEGIES=trend \
                RANGE_ENABLED_SYMBOLS= \
                TREND_ENABLED_SYMBOLS= \
                TREND_REENTRY_COOLDOWN_BARS="$cooldown" \
                TREND_EFFICIENCY_EXIT_THRESHOLD="$exit_threshold" \
                TREND_BREAKOUT_PERSISTENCE_MIN="$breakout" \
                TREND_MOMENTUM_PERSISTENCE_MIN="$momentum" \
                TREND_PULLBACK_SHALLOWNESS_MIN="$pullback" \
                TREND_HIGHER_HIGH_PERSISTENCE_MIN="$higher_high" \
                FEE_RATE="$FEE_RATE" \
                SLIPPAGE_RATE="$SLIPPAGE_RATE" \
                SPREAD_RATE="$SPREAD_RATE" \
                DELAY_BARS="$DELAY_BARS" \
                PARALLEL="$PARALLEL" \
                ./scripts/timeframe_comparison.sh

                SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
                CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
                OUT_PATH="$out_dir/timeframe_comparison_result_list.md" \
                DATA_ROOT="$data_root" \
                ./scripts/timeframe_comparison_results_list.sh
              ) &
              pids+=("$!")
              labels+=("trend-entry/$label")
              if (( ${#pids[@]} >= CASE_PARALLEL )); then
                wait_for_slot pids labels
              fi
            done
          done
        done
      done
    done
  done
  while (( ${#pids[@]} > 0 )); do
    wait_for_slot pids labels
  done
}

run_hold_exit_matrix() {
  local max_hold label out_dir data_root
  local -a pids=()
  local -a labels=()

  if [[ -n "$HOLD_EXIT_RANGE_SYMBOLS" && -n "$HOLD_EXIT_RANGE_TIMEFRAMES" && -n "$RANGE_MAX_HOLD_BARS_LIST" ]]; then
    for max_hold in ${RANGE_MAX_HOLD_BARS_LIST//,/ }; do
      label="range_hold${max_hold}"
      out_dir="$HOLD_EXIT_DIR/$label"
      data_root="$out_dir/run_data"
      (
        SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
        CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
        OUT_DIR="$out_dir" \
        DATA_ROOT="$data_root" \
        BASE_DATA_ROOT=data \
        SYMBOLS="$HOLD_EXIT_RANGE_SYMBOLS" \
        TIMEFRAMES="$HOLD_EXIT_RANGE_TIMEFRAMES" \
        STRATEGIES=range \
        RANGE_ENABLED_SYMBOLS= \
        RANGE_REQUIRE_REVERSAL_CANDLE=false \
        RANGE_WICK_RATIO_MIN=0.2 \
        RANGE_REENTRY_COOLDOWN_BARS=2 \
        RANGE_MAX_HOLD_BARS="$max_hold" \
        FEE_RATE="$FEE_RATE" \
        SLIPPAGE_RATE="$SLIPPAGE_RATE" \
        SPREAD_RATE="$SPREAD_RATE" \
        DELAY_BARS="$DELAY_BARS" \
        PARALLEL="$PARALLEL" \
        ./scripts/timeframe_comparison.sh

        SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
        CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
        OUT_PATH="$out_dir/timeframe_comparison_result_list.md" \
        DATA_ROOT="$data_root" \
        ./scripts/timeframe_comparison_results_list.sh
      ) &
      pids+=("$!")
      labels+=("hold-exit/$label")
      if (( ${#pids[@]} >= HOLD_CASE_PARALLEL )); then
        wait_for_slot pids labels
      fi
    done
  fi

  if [[ -n "$HOLD_EXIT_TREND_SYMBOLS" && -n "$HOLD_EXIT_TREND_TIMEFRAMES" && -n "$TREND_MAX_HOLD_BARS_LIST" ]]; then
    for max_hold in ${TREND_MAX_HOLD_BARS_LIST//,/ }; do
      label="trend_hold${max_hold}"
      out_dir="$HOLD_EXIT_DIR/$label"
      data_root="$out_dir/run_data"
      (
        SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
        CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
        OUT_DIR="$out_dir" \
        DATA_ROOT="$data_root" \
        BASE_DATA_ROOT=data \
        SYMBOLS="$HOLD_EXIT_TREND_SYMBOLS" \
        TIMEFRAMES="$HOLD_EXIT_TREND_TIMEFRAMES" \
        STRATEGIES=trend \
        TREND_ENABLED_SYMBOLS= \
        TREND_REENTRY_COOLDOWN_BARS=2 \
        TREND_EFFICIENCY_EXIT_THRESHOLD=0.1 \
        TREND_MAX_HOLD_BARS="$max_hold" \
        FEE_RATE="$FEE_RATE" \
        SLIPPAGE_RATE="$SLIPPAGE_RATE" \
        SPREAD_RATE="$SPREAD_RATE" \
        DELAY_BARS="$DELAY_BARS" \
        PARALLEL="$PARALLEL" \
        ./scripts/timeframe_comparison.sh

        SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
        CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
        OUT_PATH="$out_dir/timeframe_comparison_result_list.md" \
        DATA_ROOT="$data_root" \
        ./scripts/timeframe_comparison_results_list.sh
      ) &
      pids+=("$!")
      labels+=("hold-exit/$label")
      if (( ${#pids[@]} >= HOLD_CASE_PARALLEL )); then
        wait_for_slot pids labels
      fi
    done
  fi

  while (( ${#pids[@]} > 0 )); do
    wait_for_slot pids labels
  done
}

run_regime_threshold_matrix() {
  local adx breakout_hold regime_hold hv_cooldown label out_dir data_root
  local -a pids=()
  local -a labels=()

  for adx in ${REGIME_TREND_ADX_THRESHOLD_LIST//,/ }; do
    for breakout_hold in ${REGIME_TREND_BREAKOUT_PERSISTENCE_MIN_BARS_LIST//,/ }; do
      for regime_hold in ${MIN_REGIME_HOLD_BARS_LIST//,/ }; do
        for hv_cooldown in ${HIGH_VOL_COOLDOWN_BARS_LIST//,/ }; do
          label="adx${adx}_breakouthold${breakout_hold}_regimehold${regime_hold}_hvcool${hv_cooldown}"
          out_dir="$REGIME_THRESHOLD_DIR/$label"
          data_root="$out_dir/run_data"
          (
            SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
            CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
            OUT_DIR="$out_dir" \
            DATA_ROOT="$data_root" \
            BASE_DATA_ROOT=data \
            SYMBOLS="$REGIME_THRESHOLD_SYMBOLS" \
            TIMEFRAMES="$REGIME_THRESHOLD_TIMEFRAMES" \
            STRATEGIES=trend \
            TREND_ENABLED_SYMBOLS= \
            TREND_REENTRY_COOLDOWN_BARS=2 \
            TREND_EFFICIENCY_EXIT_THRESHOLD=0.1 \
            TREND_MAX_HOLD_BARS=4 \
            REGIME_TREND_ADX_THRESHOLD="$adx" \
            REGIME_TREND_BREAKOUT_PERSISTENCE_MIN_BARS="$breakout_hold" \
            MIN_REGIME_HOLD_BARS="$regime_hold" \
            HIGH_VOL_COOLDOWN_BARS="$hv_cooldown" \
            FEE_RATE="$FEE_RATE" \
            SLIPPAGE_RATE="$SLIPPAGE_RATE" \
            SPREAD_RATE="$SPREAD_RATE" \
            DELAY_BARS="$DELAY_BARS" \
            PARALLEL="$PARALLEL" \
            ./scripts/timeframe_comparison.sh

            SUMMARY_PATH="$out_dir/timeframe_comparison_summary.json" \
            CANDIDATE_REPORT_PATH="$out_dir/candidate_report.json" \
            OUT_PATH="$out_dir/timeframe_comparison_result_list.md" \
            DATA_ROOT="$data_root" \
            ./scripts/timeframe_comparison_results_list.sh

            ROUTES="$REGIME_THRESHOLD_ROUTES" \
            DATA_ROOT="$data_root" \
            OUT_PATH="$out_dir/regime_entry_diagnostics.md" \
            JSON_OUT="$out_dir/regime_entry_diagnostics.json" \
            REGIME_TREND_ADX_THRESHOLD="$adx" \
            ./scripts/regime_entry_diagnostics_report.sh
          ) &
          pids+=("$!")
          labels+=("regime-threshold/$label")
          if (( ${#pids[@]} >= REGIME_CASE_PARALLEL )); then
            wait_for_slot pids labels
          fi
        done
      done
    done
  done

  while (( ${#pids[@]} > 0 )); do
    wait_for_slot pids labels
  done
}

run_trend_entry_diagnostics() {
  ROUTES="$TREND_DIAGNOSTIC_ROUTES" \
  DATA_ROOT="$BASELINE_DATA_ROOT" \
  OUT_PATH="$TREND_ENTRY_DIAGNOSTICS_MD" \
  JSON_OUT="$TREND_ENTRY_DIAGNOSTICS_JSON" \
  TREND_MIN_ENTRY_SCORE="${TREND_MIN_ENTRY_SCORE:-1.0}" \
  ./scripts/trend_entry_diagnostics_report.sh
}

run_loss_fold_review() {
  CANDIDATE_REPORT_PATH="$BASELINE_CANDIDATE_REPORT_PATH" \
  DATA_ROOT="$BASELINE_DATA_ROOT" \
  OUT_PATH="$LOSS_FOLD_REVIEW_MD" \
  JSON_OUT="$LOSS_FOLD_REVIEW_JSON" \
  ./scripts/loss_fold_review_report.sh
}

run_loss_fold_trade_detail() {
  LOSS_FOLD_REVIEW_JSON="$LOSS_FOLD_REVIEW_JSON" \
  CANDIDATE_REPORT_PATH="$BASELINE_CANDIDATE_REPORT_PATH" \
  DATA_ROOT="$BASELINE_DATA_ROOT" \
  MAX_DETAIL_ROUTES="$LOSS_FOLD_TRADE_DETAIL_MAX_ROUTES" \
  OUT_PATH="$LOSS_FOLD_TRADE_DETAIL_MD" \
  JSON_OUT="$LOSS_FOLD_TRADE_DETAIL_JSON" \
  ./scripts/loss_fold_trade_detail_report.sh
}

run_loss_hold_threshold() {
  LOSS_FOLD_REVIEW_JSON="$LOSS_FOLD_REVIEW_JSON" \
  CANDIDATE_REPORT_PATH="$BASELINE_CANDIDATE_REPORT_PATH" \
  ANALYSIS_DIR="$BASELINE_DATA_ROOT/analysis" \
  MAX_ROUTES="$LOSS_HOLD_THRESHOLD_MAX_ROUTES" \
  THRESHOLDS_HOURS="$LOSS_HOLD_THRESHOLDS_HOURS" \
  OUT_PATH="$LOSS_HOLD_THRESHOLD_MD" \
  JSON_OUT="$LOSS_HOLD_THRESHOLD_JSON" \
  ./scripts/loss_hold_threshold_report.sh
}

build_aggregate_report() {
  "$PYTHON_BIN" - "$BASELINE_CANDIDATE_REPORT_PATH" "$RANGE_MATRIX_DIR" "$TREND_MATRIX_DIR" "$CORE_CANDIDATE_ROUTES" "$AGGREGATE_JSON" "$AGGREGATE_MD" <<'PY'
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

baseline_candidate = Path(sys.argv[1])
range_dir = Path(sys.argv[2])
trend_dir = Path(sys.argv[3])
target_routes = [item.strip() for item in sys.argv[4].split(",") if item.strip()]
json_out = Path(sys.argv[5])
md_out = Path(sys.argv[6])

baseline = json.loads(baseline_candidate.read_text(encoding="utf-8"))
baseline_rows = {
    f"{row['strategy']}:{row['symbol']}:{row['timeframe']}": row
    for row in baseline.get("rows", [])
    if isinstance(row, dict)
}

def load_candidates(root: Path) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for path in sorted(root.glob("*/candidate_report.json")):
        label = path.parent.name
        payload = json.loads(path.read_text(encoding="utf-8"))
        out.append((label, payload))
    return out

def check_count(row: dict) -> int:
    checks = [
        float(row.get("pf_mean", 0.0) or 0.0) >= 1.2,
        float(row.get("expectancy_bps_mean", 0.0) or 0.0) > 0.0,
        float(row.get("period_pnl_mean", 0.0) or 0.0) > 0.0,
        float(row.get("max_dd_mean", 0.0) or 0.0) <= 0.08,
    ]
    return sum(1 for item in checks if item)

all_runs = load_candidates(range_dir) + load_candidates(trend_dir)
route_rows: dict[str, list[dict]] = defaultdict(list)
for label, payload in all_runs:
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        route_key = f"{row['strategy']}:{row['symbol']}:{row['timeframe']}"
        if route_key not in target_routes:
            continue
        enriched = dict(row)
        enriched["config_label"] = label
        enriched["core_check_count"] = check_count(row)
        enriched["temporary_core"] = (
            str(row.get("candidate_status", "")) == "core"
            and float(row.get("closed_trades_mean", 0.0) or 0.0) < 10.0
        )
        route_rows[route_key].append(enriched)

for route_key, rows in route_rows.items():
    rows.sort(
        key=lambda row: (
            -int(row["core_check_count"]),
            -float(row.get("closed_trades_mean", 0.0) or 0.0),
            -float(row.get("expectancy_bps_mean", 0.0) or 0.0),
            str(row.get("config_label", "")),
        )
    )

payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "baseline_candidate_report": str(baseline_candidate),
    "target_routes": target_routes,
    "route_results": route_rows,
}
json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines = [
    "# Core Expansion Tuning Summary",
    "",
    f"- generated_at: {payload['generated_at']}",
    f"- baseline_candidate_report: {baseline_candidate}",
    f"- target_routes: {', '.join(target_routes)}",
    "",
]
for route_key in target_routes:
    baseline_row = baseline_rows.get(route_key, {})
    lines.append(f"## {route_key}")
    lines.append("")
    if baseline_row:
        lines.append(
            "- baseline: status={status} pf={pf:.3f} expbps={exp:.2f} pnl={pnl:.3f} dd={dd:.5f} trades={trades:.2f}".format(
                status=str(baseline_row.get("candidate_status", "-")),
                pf=float(baseline_row.get("pf_mean", 0.0) or 0.0),
                exp=float(baseline_row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(baseline_row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(baseline_row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(baseline_row.get("closed_trades_mean", 0.0) or 0.0),
            )
        )
    rows = route_rows.get(route_key, [])
    if not rows:
        lines.append("- no matrix results")
        lines.append("")
        continue
    lines.append("")
    lines.append("| Rank | Config | Status | Core Checks | Temp Core | PF | EXPbps | PeriodPnL | DD | Closed Trades |")
    lines.append("|---:|---|---|---:|---|---:|---:|---:|---:|---:|")
    for idx, row in enumerate(rows[:10], start=1):
        lines.append(
            "| {rank} | {config} | {status} | {checks} | {temp} | {pf:.3f} | {exp:.2f} | {pnl:.3f} | {dd:.5f} | {trades:.2f} |".format(
                rank=idx,
                config=str(row.get("config_label", "")),
                status=str(row.get("candidate_status", "")),
                checks=int(row.get("core_check_count", 0) or 0),
                temp="yes" if bool(row.get("temporary_core")) else "no",
                pf=float(row.get("pf_mean", 0.0) or 0.0),
                exp=float(row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(row.get("closed_trades_mean", 0.0) or 0.0),
            )
        )
    lines.append("")

md_out.write_text("\n".join(lines), encoding="utf-8")
print(json_out)
print(md_out)
PY
}

build_trend_next_step_report() {
  "$PYTHON_BIN" - "$BASELINE_CANDIDATE_REPORT_PATH" "$TREND_NEXT_STEP_DIR" "$TREND_NEXT_STEP_ROUTES" "$TREND_NEXT_STEP_JSON" "$TREND_NEXT_STEP_MD" <<'PY'
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

baseline_candidate = Path(sys.argv[1])
matrix_dir = Path(sys.argv[2])
target_routes = [item.strip() for item in sys.argv[3].split(",") if item.strip()]
json_out = Path(sys.argv[4])
md_out = Path(sys.argv[5])

baseline = json.loads(baseline_candidate.read_text(encoding="utf-8"))
baseline_rows = {
    f"{row['strategy']}:{row['symbol']}:{row['timeframe']}": row
    for row in baseline.get("rows", [])
    if isinstance(row, dict)
}

def check_count(row: dict) -> int:
    checks = [
        float(row.get("pf_mean", 0.0) or 0.0) >= 1.2,
        float(row.get("expectancy_bps_mean", 0.0) or 0.0) > 0.0,
        float(row.get("period_pnl_mean", 0.0) or 0.0) > 0.0,
        float(row.get("max_dd_mean", 0.0) or 0.0) <= 0.08,
    ]
    return sum(1 for item in checks if item)

route_rows: dict[str, list[dict]] = defaultdict(list)
for path in sorted(matrix_dir.glob("*/candidate_report.json")):
    label = path.parent.name
    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        route_key = f"{row['strategy']}:{row['symbol']}:{row['timeframe']}"
        if route_key not in target_routes:
            continue
        enriched = dict(row)
        enriched["config_label"] = label
        enriched["core_check_count"] = check_count(row)
        route_rows[route_key].append(enriched)

for route_key, rows in route_rows.items():
    rows.sort(
        key=lambda row: (
            -int(row["core_check_count"]),
            -float(row.get("period_pnl_mean", 0.0) or 0.0),
            -float(row.get("expectancy_bps_mean", 0.0) or 0.0),
            -float(row.get("closed_trades_mean", 0.0) or 0.0),
            str(row.get("config_label", "")),
        )
    )

payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "baseline_candidate_report": str(baseline_candidate),
    "target_routes": target_routes,
    "route_results": route_rows,
}
json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines = [
    "# Trend Next Step Summary",
    "",
    f"- generated_at: {payload['generated_at']}",
    f"- baseline_candidate_report: {baseline_candidate}",
    f"- target_routes: {', '.join(target_routes)}",
    "",
]
for route_key in target_routes:
    baseline_row = baseline_rows.get(route_key, {})
    lines.append(f"## {route_key}")
    lines.append("")
    if baseline_row:
        lines.append(
            "- baseline: status={status} pf={pf:.3f} expbps={exp:.2f} pnl={pnl:.3f} dd={dd:.5f} trades={trades:.2f}".format(
                status=str(baseline_row.get("candidate_status", "-")),
                pf=float(baseline_row.get("pf_mean", 0.0) or 0.0),
                exp=float(baseline_row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(baseline_row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(baseline_row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(baseline_row.get("closed_trades_mean", 0.0) or 0.0),
            )
        )
    rows = route_rows.get(route_key, [])
    if not rows:
        lines.append("- no matrix results")
        lines.append("")
        continue
    lines.append("")
    lines.append("| Rank | Config | Status | Core Checks | PF | EXPbps | PeriodPnL | DD | Closed Trades |")
    lines.append("|---:|---|---|---:|---:|---:|---:|---:|---:|")
    for idx, row in enumerate(rows[:12], start=1):
        lines.append(
            "| {rank} | {config} | {status} | {checks} | {pf:.3f} | {exp:.2f} | {pnl:.3f} | {dd:.5f} | {trades:.2f} |".format(
                rank=idx,
                config=str(row.get("config_label", "")),
                status=str(row.get("candidate_status", "")),
                checks=int(row.get("core_check_count", 0) or 0),
                pf=float(row.get("pf_mean", 0.0) or 0.0),
                exp=float(row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(row.get("closed_trades_mean", 0.0) or 0.0),
            )
        )
    lines.append("")

md_out.write_text("\n".join(lines), encoding="utf-8")
print(json_out)
print(md_out)
PY
}

build_trend_entry_threshold_report() {
  "$PYTHON_BIN" - "$BASELINE_CANDIDATE_REPORT_PATH" "$TREND_ENTRY_THRESHOLD_DIR" "$TREND_ENTRY_THRESHOLD_ROUTES" "$TREND_ENTRY_THRESHOLD_JSON" "$TREND_ENTRY_THRESHOLD_MD" <<'PY'
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

baseline_candidate = Path(sys.argv[1])
matrix_dir = Path(sys.argv[2])
target_routes = [item.strip() for item in sys.argv[3].split(",") if item.strip()]
json_out = Path(sys.argv[4])
md_out = Path(sys.argv[5])

baseline = json.loads(baseline_candidate.read_text(encoding="utf-8"))
baseline_rows = {
    f"{row['strategy']}:{row['symbol']}:{row['timeframe']}": row
    for row in baseline.get("rows", [])
    if isinstance(row, dict)
}

def check_count(row: dict) -> int:
    checks = [
        float(row.get("pf_mean", 0.0) or 0.0) >= 1.2,
        float(row.get("expectancy_bps_mean", 0.0) or 0.0) > 0.0,
        float(row.get("period_pnl_mean", 0.0) or 0.0) > 0.0,
        float(row.get("max_dd_mean", 0.0) or 0.0) <= 0.08,
    ]
    return sum(1 for item in checks if item)

route_rows: dict[str, list[dict]] = defaultdict(list)
for path in sorted(matrix_dir.glob("*/candidate_report.json")):
    label = path.parent.name
    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        route_key = f"{row['strategy']}:{row['symbol']}:{row['timeframe']}"
        if route_key not in target_routes:
            continue
        enriched = dict(row)
        enriched["config_label"] = label
        enriched["core_check_count"] = check_count(row)
        enriched["temporary_core"] = (
            str(row.get("candidate_status", "")) == "core"
            and float(row.get("closed_trades_mean", 0.0) or 0.0) < 10.0
        )
        route_rows[route_key].append(enriched)

for route_key, rows in route_rows.items():
    rows.sort(
        key=lambda row: (
            -int(row["core_check_count"]),
            -float(row.get("closed_trades_mean", 0.0) or 0.0),
            -float(row.get("expectancy_bps_mean", 0.0) or 0.0),
            -float(row.get("period_pnl_mean", 0.0) or 0.0),
            str(row.get("config_label", "")),
        )
    )

payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "baseline_candidate_report": str(baseline_candidate),
    "target_routes": target_routes,
    "route_results": route_rows,
}
json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines = [
    "# Trend Entry Threshold Summary",
    "",
    f"- generated_at: {payload['generated_at']}",
    f"- baseline_candidate_report: {baseline_candidate}",
    f"- target_routes: {', '.join(target_routes)}",
    "",
]
for route_key in target_routes:
    baseline_row = baseline_rows.get(route_key, {})
    lines.append(f"## {route_key}")
    lines.append("")
    if baseline_row:
        lines.append(
            "- baseline: status={status} pf={pf:.3f} expbps={exp:.2f} pnl={pnl:.3f} dd={dd:.5f} trades={trades:.2f}".format(
                status=str(baseline_row.get("candidate_status", "-")),
                pf=float(baseline_row.get("pf_mean", 0.0) or 0.0),
                exp=float(baseline_row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(baseline_row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(baseline_row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(baseline_row.get("closed_trades_mean", 0.0) or 0.0),
            )
        )
    rows = route_rows.get(route_key, [])
    if not rows:
        lines.append("- no matrix results")
        lines.append("")
        continue
    lines.append("")
    lines.append("| Rank | Config | Status | Core Checks | Temp Core | PF | EXPbps | PeriodPnL | DD | Closed Trades |")
    lines.append("|---:|---|---|---:|---|---:|---:|---:|---:|---:|")
    for idx, row in enumerate(rows[:15], start=1):
        lines.append(
            "| {rank} | {config} | {status} | {checks} | {temp} | {pf:.3f} | {exp:.2f} | {pnl:.3f} | {dd:.5f} | {trades:.2f} |".format(
                rank=idx,
                config=str(row.get("config_label", "")),
                status=str(row.get("candidate_status", "")),
                checks=int(row.get("core_check_count", 0) or 0),
                temp="yes" if bool(row.get("temporary_core")) else "no",
                pf=float(row.get("pf_mean", 0.0) or 0.0),
                exp=float(row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(row.get("closed_trades_mean", 0.0) or 0.0),
            )
        )
    lines.append("")

md_out.write_text("\n".join(lines), encoding="utf-8")
print(json_out)
print(md_out)
PY
}

build_hold_exit_report() {
  "$PYTHON_BIN" - "$BASELINE_CANDIDATE_REPORT_PATH" "$HOLD_EXIT_DIR" "$HOLD_EXIT_ROUTES" "$HOLD_EXIT_JSON" "$HOLD_EXIT_MD" <<'PY'
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

baseline_candidate = Path(sys.argv[1])
matrix_dir = Path(sys.argv[2])
target_routes = [item.strip() for item in sys.argv[3].split(",") if item.strip()]
json_out = Path(sys.argv[4])
md_out = Path(sys.argv[5])

baseline = json.loads(baseline_candidate.read_text(encoding="utf-8"))
baseline_rows = {
    f"{row['strategy']}:{row['symbol']}:{row['timeframe']}": row
    for row in baseline.get("rows", [])
    if isinstance(row, dict)
}

def check_count(row: dict) -> int:
    checks = [
        float(row.get("pf_mean", 0.0) or 0.0) >= 1.2,
        float(row.get("expectancy_bps_mean", 0.0) or 0.0) > 0.0,
        float(row.get("period_pnl_mean", 0.0) or 0.0) > 0.0,
        float(row.get("max_dd_mean", 0.0) or 0.0) <= 0.08,
    ]
    return sum(1 for item in checks if item)

route_rows: dict[str, list[dict]] = defaultdict(list)
for path in sorted(matrix_dir.glob("*/candidate_report.json")):
    label = path.parent.name
    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        route_key = f"{row['strategy']}:{row['symbol']}:{row['timeframe']}"
        if route_key not in target_routes:
            continue
        enriched = dict(row)
        enriched["config_label"] = label
        enriched["core_check_count"] = check_count(row)
        route_rows[route_key].append(enriched)

for route_key, rows in route_rows.items():
    rows.sort(
        key=lambda row: (
            -int(row["core_check_count"]),
            -float(row.get("period_pnl_mean", 0.0) or 0.0),
            -float(row.get("expectancy_bps_mean", 0.0) or 0.0),
            -float(row.get("closed_trades_mean", 0.0) or 0.0),
            str(row.get("config_label", "")),
        )
    )

payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "baseline_candidate_report": str(baseline_candidate),
    "target_routes": target_routes,
    "route_results": route_rows,
}
json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines = [
    "# Hold Exit Summary",
    "",
    f"- generated_at: {payload['generated_at']}",
    f"- baseline_candidate_report: {baseline_candidate}",
    f"- target_routes: {', '.join(target_routes)}",
    "",
]
for route_key in target_routes:
    baseline_row = baseline_rows.get(route_key, {})
    lines.append(f"## {route_key}")
    lines.append("")
    if baseline_row:
        lines.append(
            "- baseline: status={status} pf={pf:.3f} expbps={exp:.2f} pnl={pnl:.3f} dd={dd:.5f} trades={trades:.2f}".format(
                status=str(baseline_row.get("candidate_status", "-")),
                pf=float(baseline_row.get("pf_mean", 0.0) or 0.0),
                exp=float(baseline_row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(baseline_row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(baseline_row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(baseline_row.get("closed_trades_mean", 0.0) or 0.0),
            )
        )
    rows = route_rows.get(route_key, [])
    if not rows:
        lines.append("- no matrix results")
        lines.append("")
        continue
    lines.append("")
    lines.append("| Rank | Config | Status | Core Checks | PF | EXPbps | PeriodPnL | DD | Closed Trades |")
    lines.append("|---:|---|---|---:|---:|---:|---:|---:|---:|")
    for idx, row in enumerate(rows[:10], start=1):
        lines.append(
            "| {rank} | {config} | {status} | {checks} | {pf:.3f} | {exp:.2f} | {pnl:.3f} | {dd:.5f} | {trades:.2f} |".format(
                rank=idx,
                config=str(row.get("config_label", "")),
                status=str(row.get("candidate_status", "")),
                checks=int(row.get("core_check_count", 0) or 0),
                pf=float(row.get("pf_mean", 0.0) or 0.0),
                exp=float(row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(row.get("closed_trades_mean", 0.0) or 0.0),
            )
        )
    lines.append("")

md_out.write_text("\n".join(lines), encoding="utf-8")
print(json_out)
print(md_out)
PY
}

build_regime_threshold_report() {
  "$PYTHON_BIN" - "$BASELINE_CANDIDATE_REPORT_PATH" "$REGIME_THRESHOLD_DIR" "$REGIME_THRESHOLD_ROUTES" "$REGIME_THRESHOLD_JSON" "$REGIME_THRESHOLD_MD" <<'PY'
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

baseline_candidate = Path(sys.argv[1])
matrix_dir = Path(sys.argv[2])
target_routes = [item.strip() for item in sys.argv[3].split(",") if item.strip()]
json_out = Path(sys.argv[4])
md_out = Path(sys.argv[5])

baseline = json.loads(baseline_candidate.read_text(encoding="utf-8"))
baseline_rows = {
    f"{row['strategy']}:{row['symbol']}:{row['timeframe']}": row
    for row in baseline.get("rows", [])
    if isinstance(row, dict)
}

def check_count(row: dict) -> int:
    checks = [
        float(row.get("pf_mean", 0.0) or 0.0) >= 1.2,
        float(row.get("expectancy_bps_mean", 0.0) or 0.0) > 0.0,
        float(row.get("period_pnl_mean", 0.0) or 0.0) > 0.0,
        float(row.get("max_dd_mean", 0.0) or 0.0) <= 0.08,
    ]
    return sum(1 for item in checks if item)

route_rows: dict[str, list[dict]] = defaultdict(list)
for path in sorted(matrix_dir.glob("*/candidate_report.json")):
    label = path.parent.name
    payload = json.loads(path.read_text(encoding="utf-8"))
    diag_path = path.parent / "regime_entry_diagnostics.json"
    diag_rows = {}
    if diag_path.exists():
        diag_payload = json.loads(diag_path.read_text(encoding="utf-8"))
        diag_rows = {
            str(row.get("route", "")): row
            for row in diag_payload.get("routes", [])
            if isinstance(row, dict)
        }
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        route_key = f"{row['strategy']}:{row['symbol']}:{row['timeframe']}"
        if route_key not in target_routes:
            continue
        enriched = dict(row)
        enriched["config_label"] = label
        enriched["core_check_count"] = check_count(row)
        diag = diag_rows.get(route_key, {})
        enriched["trend_regime_rows"] = int(diag.get("trend_regime_rows", 0) or 0)
        enriched["gate_open_rows"] = int(diag.get("gate_open_rows", 0) or 0)
        enriched["entry_rows"] = int(diag.get("entry_rows", 0) or 0)
        enriched["regime_trend_mask_rows"] = int(diag.get("regime_trend_mask_rows", 0) or 0)
        enriched["trend_mask_not_adopted_rows"] = int(
            diag.get("trend_mask_not_adopted_rows", 0) or 0
        )
        route_rows[route_key].append(enriched)

for route_key, rows in route_rows.items():
    rows.sort(
        key=lambda row: (
            -int(row["core_check_count"]),
            -float(row.get("pf_mean", 0.0) or 0.0),
            -float(row.get("expectancy_bps_mean", 0.0) or 0.0),
            -float(row.get("period_pnl_mean", 0.0) or 0.0),
            -int(row.get("trend_regime_rows", 0) or 0),
            str(row.get("config_label", "")),
        )
    )

payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "baseline_candidate_report": str(baseline_candidate),
    "target_routes": target_routes,
    "route_results": route_rows,
}
json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines = [
    "# Regime Threshold Summary",
    "",
    f"- generated_at: {payload['generated_at']}",
    f"- baseline_candidate_report: {baseline_candidate}",
    f"- target_routes: {', '.join(target_routes)}",
    "",
]
for route_key in target_routes:
    baseline_row = baseline_rows.get(route_key, {})
    lines.append(f"## {route_key}")
    lines.append("")
    if baseline_row:
        lines.append(
            "- baseline: status={status} pf={pf:.3f} expbps={exp:.2f} pnl={pnl:.3f} dd={dd:.5f} trades={trades:.2f}".format(
                status=str(baseline_row.get("candidate_status", "-")),
                pf=float(baseline_row.get("pf_mean", 0.0) or 0.0),
                exp=float(baseline_row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(baseline_row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(baseline_row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(baseline_row.get("closed_trades_mean", 0.0) or 0.0),
            )
        )
    rows = route_rows.get(route_key, [])
    if not rows:
        lines.append("- no matrix results")
        lines.append("")
        continue
    lines.append("")
    lines.append("| Rank | Config | Status | Core Checks | PF | EXPbps | PeriodPnL | DD | Trades | Trend Regime Rows | Trend Mask Not Adopted | Entries |")
    lines.append("|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for idx, row in enumerate(rows[:15], start=1):
        lines.append(
            "| {rank} | {config} | {status} | {checks} | {pf:.3f} | {exp:.2f} | {pnl:.3f} | {dd:.5f} | {trades:.2f} | {trend_regime} | {not_adopted} | {entries} |".format(
                rank=idx,
                config=str(row.get("config_label", "")),
                status=str(row.get("candidate_status", "")),
                checks=int(row.get("core_check_count", 0) or 0),
                pf=float(row.get("pf_mean", 0.0) or 0.0),
                exp=float(row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(row.get("closed_trades_mean", 0.0) or 0.0),
                trend_regime=int(row.get("trend_regime_rows", 0) or 0),
                not_adopted=int(row.get("trend_mask_not_adopted_rows", 0) or 0),
                entries=int(row.get("entry_rows", 0) or 0),
            )
        )
    lines.append("")

md_out.write_text("\n".join(lines), encoding="utf-8")
print(json_out)
print(md_out)
PY
}

build_range_quality_report() {
  "$PYTHON_BIN" - "$BASELINE_CANDIDATE_REPORT_PATH" "$RANGE_QUALITY_DIR" "$RANGE_QUALITY_SYMBOLS" "$RANGE_QUALITY_TIMEFRAMES" "$RANGE_QUALITY_JSON" "$RANGE_QUALITY_MD" <<'PY'
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

baseline_candidate = Path(sys.argv[1])
matrix_dir = Path(sys.argv[2])
symbols = [s.strip() for s in sys.argv[3].split(",") if s.strip()]
timeframes = [t.strip() for t in sys.argv[4].split(",") if t.strip()]
json_out = Path(sys.argv[5])
md_out = Path(sys.argv[6])

target_routes = [f"range:{sym}:{tf}" for sym in symbols for tf in timeframes]

baseline_rows: dict[str, dict] = {}
if baseline_candidate.exists():
    baseline = json.loads(baseline_candidate.read_text(encoding="utf-8"))
    baseline_rows = {
        f"{row['strategy']}:{row['symbol']}:{row['timeframe']}": row
        for row in baseline.get("rows", [])
        if isinstance(row, dict)
    }

def check_count(row: dict) -> int:
    checks = [
        float(row.get("pf_mean", 0.0) or 0.0) >= 1.2,
        float(row.get("expectancy_bps_mean", 0.0) or 0.0) > 0.0,
        float(row.get("period_pnl_mean", 0.0) or 0.0) > 0.0,
        float(row.get("max_dd_mean", 0.0) or 0.0) <= 0.08,
    ]
    return sum(1 for item in checks if item)

route_rows: dict[str, list[dict]] = defaultdict(list)
for path in sorted(matrix_dir.glob("*/candidate_report.json")):
    label = path.parent.name
    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        route_key = f"{row['strategy']}:{row['symbol']}:{row['timeframe']}"
        if route_key not in target_routes:
            continue
        enriched = dict(row)
        enriched["config_label"] = label
        enriched["core_check_count"] = check_count(row)
        route_rows[route_key].append(enriched)

for route_key, rows in route_rows.items():
    rows.sort(
        key=lambda row: (
            -int(row["core_check_count"]),
            -float(row.get("pf_mean", 0.0) or 0.0),
            -float(row.get("expectancy_bps_mean", 0.0) or 0.0),
            -float(row.get("period_pnl_mean", 0.0) or 0.0),
            str(row.get("config_label", "")),
        )
    )

payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "baseline_candidate_report": str(baseline_candidate),
    "target_routes": target_routes,
    "route_results": route_rows,
}
json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines = [
    "# Range Quality Matrix Summary",
    "",
    f"- generated_at: {payload['generated_at']}",
    f"- baseline_candidate_report: {baseline_candidate}",
    f"- target_routes: {', '.join(target_routes)}",
    "",
]
for route_key in target_routes:
    baseline_row = baseline_rows.get(route_key, {})
    lines.append(f"## {route_key}")
    lines.append("")
    if baseline_row:
        lines.append(
            "- baseline: status={status} pf={pf:.3f} expbps={exp:.2f} pnl={pnl:.3f} dd={dd:.5f} trades={trades:.2f}".format(
                status=str(baseline_row.get("candidate_status", "-")),
                pf=float(baseline_row.get("pf_mean", 0.0) or 0.0),
                exp=float(baseline_row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(baseline_row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(baseline_row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(baseline_row.get("closed_trades_mean", 0.0) or 0.0),
            )
        )
    rows = route_rows.get(route_key, [])
    if not rows:
        lines.append("- no matrix results")
        lines.append("")
        continue
    lines.append("")
    lines.append("| Rank | Config | Status | Core Checks | PF | EXPbps | PeriodPnL | DD | Trades |")
    lines.append("|---:|---|---|---:|---:|---:|---:|---:|---:|")
    for idx, row in enumerate(rows[:15], start=1):
        lines.append(
            "| {rank} | {config} | {status} | {checks} | {pf:.3f} | {exp:.2f} | {pnl:.3f} | {dd:.5f} | {trades:.2f} |".format(
                rank=idx,
                config=str(row.get("config_label", "")),
                status=str(row.get("candidate_status", "")),
                checks=int(row.get("core_check_count", 0) or 0),
                pf=float(row.get("pf_mean", 0.0) or 0.0),
                exp=float(row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(row.get("closed_trades_mean", 0.0) or 0.0),
            )
        )
    lines.append("")

md_out.write_text("\n".join(lines), encoding="utf-8")
print(json_out)
print(md_out)
PY
}

build_trend_provisional_core_report() {
  "$PYTHON_BIN" - "$BASELINE_CANDIDATE_REPORT_PATH" "$TREND_PROVISIONAL_CORE_DIR" "$TREND_PROVISIONAL_CORE_ROUTES" "$TREND_PROVISIONAL_CORE_JSON" "$TREND_PROVISIONAL_CORE_MD" <<'PY'
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

baseline_candidate = Path(sys.argv[1])
matrix_dir = Path(sys.argv[2])
target_routes = [item.strip() for item in sys.argv[3].split(",") if item.strip()]
json_out = Path(sys.argv[4])
md_out = Path(sys.argv[5])

baseline = json.loads(baseline_candidate.read_text(encoding="utf-8"))
baseline_rows = {
    f"{row['strategy']}:{row['symbol']}:{row['timeframe']}": row
    for row in baseline.get("rows", [])
    if isinstance(row, dict)
}

def check_count(row: dict) -> int:
    checks = [
        float(row.get("pf_mean", 0.0) or 0.0) >= 1.2,
        float(row.get("expectancy_bps_mean", 0.0) or 0.0) > 0.0,
        float(row.get("period_pnl_mean", 0.0) or 0.0) > 0.0,
        float(row.get("max_dd_mean", 0.0) or 0.0) <= 0.08,
    ]
    return sum(1 for item in checks if item)

route_rows: dict[str, list[dict]] = defaultdict(list)
for path in sorted(matrix_dir.glob("*/candidate_report.json")):
    label = path.parent.name
    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        route_key = f"{row['strategy']}:{row['symbol']}:{row['timeframe']}"
        if route_key not in target_routes:
            continue
        enriched = dict(row)
        enriched["config_label"] = label
        enriched["core_check_count"] = check_count(row)
        enriched["temporary_core"] = (
            str(row.get("candidate_status", "")) == "core"
            and float(row.get("closed_trades_mean", 0.0) or 0.0) < 10.0
        )
        route_rows[route_key].append(enriched)

for route_key, rows in route_rows.items():
    rows.sort(
        key=lambda row: (
            -int(row["core_check_count"]),
            -float(row.get("closed_trades_mean", 0.0) or 0.0),
            -float(row.get("expectancy_bps_mean", 0.0) or 0.0),
            -float(row.get("period_pnl_mean", 0.0) or 0.0),
            str(row.get("config_label", "")),
        )
    )

payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "baseline_candidate_report": str(baseline_candidate),
    "target_routes": target_routes,
    "route_results": route_rows,
}
json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines = [
    "# Trend Provisional Core Summary",
    "",
    f"- generated_at: {payload['generated_at']}",
    f"- baseline_candidate_report: {baseline_candidate}",
    f"- target_routes: {', '.join(target_routes)}",
    "",
]
for route_key in target_routes:
    baseline_row = baseline_rows.get(route_key, {})
    lines.append(f"## {route_key}")
    lines.append("")
    if baseline_row:
        lines.append(
            "- baseline: status={status} pf={pf:.3f} expbps={exp:.2f} pnl={pnl:.3f} dd={dd:.5f} trades={trades:.2f}".format(
                status=str(baseline_row.get("candidate_status", "-")),
                pf=float(baseline_row.get("pf_mean", 0.0) or 0.0),
                exp=float(baseline_row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(baseline_row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(baseline_row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(baseline_row.get("closed_trades_mean", 0.0) or 0.0),
            )
        )
    rows = route_rows.get(route_key, [])
    if not rows:
        lines.append("- no matrix results")
        lines.append("")
        continue
    lines.append("")
    lines.append("| Rank | Config | Status | Core Checks | Temp Core | PF | EXPbps | PeriodPnL | DD | Closed Trades |")
    lines.append("|---:|---|---|---:|---|---:|---:|---:|---:|---:|")
    for idx, row in enumerate(rows[:15], start=1):
        lines.append(
            "| {rank} | {config} | {status} | {checks} | {temp} | {pf:.3f} | {exp:.2f} | {pnl:.3f} | {dd:.5f} | {trades:.2f} |".format(
                rank=idx,
                config=str(row.get("config_label", "")),
                status=str(row.get("candidate_status", "")),
                checks=int(row.get("core_check_count", 0) or 0),
                temp="yes" if bool(row.get("temporary_core")) else "no",
                pf=float(row.get("pf_mean", 0.0) or 0.0),
                exp=float(row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(row.get("closed_trades_mean", 0.0) or 0.0),
            )
        )
    lines.append("")

md_out.write_text("\n".join(lines), encoding="utf-8")
print(json_out)
print(md_out)
PY
}

if [[ "$RUN_BASELINE" == "1" ]]; then
  run_baseline
fi
if [[ "$RUN_RANGE_MATRIX" == "1" ]]; then
  run_range_matrix
fi
if [[ "$RUN_RANGE_QUALITY_MATRIX" == "1" ]]; then
  run_range_quality_matrix
fi
if [[ "$RUN_RANGE_REGIME_THRESHOLD_MATRIX" == "1" ]]; then
  run_range_regime_threshold_matrix
fi
if [[ "$RUN_TREND_MATRIX" == "1" ]]; then
  run_trend_matrix
fi
if [[ "$RUN_TREND_NEXT_STEP_MATRIX" == "1" ]]; then
  run_trend_next_step_matrix
fi
if [[ "$RUN_TREND_PROVISIONAL_CORE_MATRIX" == "1" ]]; then
  run_trend_provisional_core_matrix
fi
if [[ "$RUN_TREND_ENTRY_THRESHOLD_MATRIX" == "1" ]]; then
  run_trend_entry_threshold_matrix
fi
if [[ "$RUN_HOLD_EXIT_MATRIX" == "1" ]]; then
  run_hold_exit_matrix
fi
if [[ "$RUN_REGIME_THRESHOLD_MATRIX" == "1" ]]; then
  run_regime_threshold_matrix
fi

if [[ "$RUN_FOLD_BREAKDOWN" == "1" ]]; then
  ROUTES="$LOGIC_REVIEW_ROUTES" DATA_ROOT="$BASELINE_DATA_ROOT" OUT_PATH="$FOLD_BREAKDOWN_MD" ./scripts/walkforward_fold_breakdown_report.sh
fi
if [[ "$RUN_TREND_ENTRY_DIAGNOSTICS" == "1" ]]; then
  run_trend_entry_diagnostics
fi
if [[ "$RUN_LOSS_FOLD_REVIEW" == "1" ]]; then
  run_loss_fold_review
fi
if [[ "$RUN_LOSS_FOLD_TRADE_DETAIL" == "1" ]]; then
  run_loss_fold_trade_detail
fi
if [[ "$RUN_LOSS_HOLD_THRESHOLD" == "1" ]]; then
  run_loss_hold_threshold
fi
if [[ "$RUN_BUILD_AGGREGATE_REPORT" == "1" ]]; then
  build_aggregate_report
fi
if [[ "$RUN_BUILD_TREND_NEXT_STEP_REPORT" == "1" ]]; then
  build_trend_next_step_report
fi
if [[ "$RUN_BUILD_TREND_PROVISIONAL_CORE_REPORT" == "1" ]]; then
  build_trend_provisional_core_report
fi
if [[ "$RUN_BUILD_TREND_ENTRY_THRESHOLD_REPORT" == "1" ]]; then
  build_trend_entry_threshold_report
fi
if [[ "$RUN_BUILD_HOLD_EXIT_REPORT" == "1" ]]; then
  build_hold_exit_report
fi
if [[ "$RUN_BUILD_REGIME_THRESHOLD_REPORT" == "1" ]]; then
  build_regime_threshold_report
fi
if [[ "$RUN_BUILD_RANGE_QUALITY_REPORT" == "1" ]]; then
  build_range_quality_report
fi

echo "done: $OUT_DIR"
