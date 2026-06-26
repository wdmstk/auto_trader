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

# Extended parameter ranges based on analysis
EXTENDED_RSI_MIN_LIST="${EXTENDED_RSI_MIN_LIST:-30,32,35,38,40}"
EXTENDED_RSI_MAX_LIST="${EXTENDED_RSI_MAX_LIST:-45,48,50,52,55,58}"
EXTENDED_SR_SUPPORT_DISTANCE_MAX_LIST="${EXTENDED_SR_SUPPORT_DISTANCE_MAX_LIST:-0.5,0.8,1.0,1.2,1.5,1.8,2.0,2.5}"
EXTENDED_SR_MIN_LEVEL_STRENGTH_LIST="${EXTENDED_SR_MIN_LEVEL_STRENGTH_LIST:-2,3,4,5}"
EXTENDED_MIN_ENTRY_SCORE_LIST="${EXTENDED_MIN_ENTRY_SCORE_LIST:-0.55,0.6,0.65,0.7,0.75,0.8}"
EXTENDED_SR_RESISTANCE_EXIT_ATR_LIST="${EXTENDED_SR_RESISTANCE_EXIT_ATR_LIST:-0.3,0.4,0.5,0.6,0.7}"
EXTENDED_W_SR_PROXIMITY_LIST="${EXTENDED_W_SR_PROXIMITY_LIST:-1.5,2.0,2.5,3.0}"
EXTENDED_W_SR_STRENGTH_LIST="${EXTENDED_W_SR_STRENGTH_LIST:-1.0,1.5,2.0,2.5}"

# Focus on ETHUSDT 30m first (best performer)
EXTENDED_SYMBOLS="${EXTENDED_SYMBOLS:-ETHUSDT}"
EXTENDED_TIMEFRAMES="${EXTENDED_TIMEFRAMES:-30m}"

OUTPUT_DIR="${OUTPUT_DIR:-data/validation/extended_range_tuning}"
mkdir -p "$OUTPUT_DIR"

echo "Starting extended Range strategy parameter tuning..."
echo "Symbols: $EXTENDED_SYMBOLS"
echo "Timeframes: $EXTENDED_TIMEFRAMES"
echo "Output directory: $OUTPUT_DIR"

# Generate parameter combinations
total_combinations=1
total_combinations=$((total_combinations * $(echo "$EXTENDED_RSI_MIN_LIST" | tr ',' '\n' | wc -l)))
total_combinations=$((total_combinations * $(echo "$EXTENDED_RSI_MAX_LIST" | tr ',' '\n' | wc -l)))
total_combinations=$((total_combinations * $(echo "$EXTENDED_SR_SUPPORT_DISTANCE_MAX_LIST" | tr ',' '\n' | wc -l)))
total_combinations=$((total_combinations * $(echo "$EXTENDED_SR_MIN_LEVEL_STRENGTH_LIST" | tr ',' '\n' | wc -l)))
total_combinations=$((total_combinations * $(echo "$EXTENDED_MIN_ENTRY_SCORE_LIST" | tr ',' '\n' | wc -l)))

echo "Total parameter combinations: $total_combinations"

# Create parameter matrix
echo "Generating parameter matrix..."
IFS=',' read -ra RSI_MIN_ARR <<< "$EXTENDED_RSI_MIN_LIST"
IFS=',' read -ra RSI_MAX_ARR <<< "$EXTENDED_RSI_MAX_LIST"
IFS=',' read -ra SR_DIST_ARR <<< "$EXTENDED_SR_SUPPORT_DISTANCE_MAX_LIST"
IFS=',' read -ra SR_STR_ARR <<< "$EXTENDED_SR_MIN_LEVEL_STRENGTH_LIST"
IFS=',' read -ra SCORE_ARR <<< "$EXTENDED_MIN_ENTRY_SCORE_LIST"

combination_count=0
for rsi_min in "${RSI_MIN_ARR[@]}"; do
  for rsi_max in "${RSI_MAX_ARR[@]}"; do
    # Only consider valid RSI ranges (min < max)
    # Use python for reliable float comparison
    if ! "$PYTHON_BIN" -c "exit(0 if float('$rsi_min') < float('$rsi_max') else 1)"; then
      continue
    fi

    for sr_dist in "${SR_DIST_ARR[@]}"; do
      for sr_str in "${SR_STR_ARR[@]}"; do
        for score in "${SCORE_ARR[@]}"; do
          combination_count=$((combination_count + 1))

          # Create config label
          config_label="rsi${rsi_min}-${rsi_max}_srd${sr_dist}_srs${sr_str}_score${score}"
          config_dir="$OUTPUT_DIR/$config_label"
          mkdir -p "$config_dir"

          # Generate config file
          cat > "$config_dir/config.json" <<EOF
{
  "strategy": "range",
  "rsi_min": $rsi_min,
  "rsi_max": $rsi_max,
  "sr_support_distance_max": $sr_dist,
  "sr_min_level_strength": $sr_str,
  "min_entry_score": $score,
  "sr_resistance_exit_atr": 0.5,
  "w_sr_proximity": 2.0,
  "w_sr_strength": 1.5,
  "symbols": ["$EXTENDED_SYMBOLS"],
  "timeframes": ["$EXTENDED_TIMEFRAMES"]
}
EOF

          echo "Generated config $combination_count/$total_combinations: $config_label"
        done
      done
    done
  done
done

echo "Generated $combination_count parameter combinations"
echo "Config files saved to: $OUTPUT_DIR"

# Summary
echo ""
echo "Extended Range Tuning Setup Complete"
echo "===================================="
echo "Parameter ranges:"
echo "  RSI min: $EXTENDED_RSI_MIN_LIST"
echo "  RSI max: $EXTENDED_RSI_MAX_LIST"
echo "  S/R distance: $EXTENDED_SR_SUPPORT_DISTANCE_MAX_LIST"
echo "  S/R strength: $EXTENDED_SR_MIN_LEVEL_STRENGTH_LIST"
echo "  Entry score: $EXTENDED_MIN_ENTRY_SCORE_LIST"
echo ""
echo "Next steps:"
echo "1. Run validation for each config using the main validation pipeline"
echo "2. Analyze results and identify best performing parameters"
echo "3. Focus on ETHUSDT 30m optimization based on findings"
