# Phase 5d: Higher-Timeframe S/R Level Detection for Range Strategy

## Background

Phase 5c implemented S/R level reversal logic but produced worse results than BB
regression (PF 0.35–0.66 vs 0.6–0.74 for BB). Root cause: pivot detection on 15m/30m
generates excessive noise — too many spurious levels with weak significance.

Traditional S/R works best on higher timeframes where levels represent genuine
institutional order clusters, not intrabar noise.

## Goal

Detect S/R levels on 4h (or 1h) timeframes where pivots are structurally meaningful,
then evaluate proximity and entry signals on 15m/30m execution timeframes.

**Quality gates**: PF >= 1.2, DD <= 0.08, min 30 trades per fold.

## Design

### Architecture

```
                ┌──────────────────┐
                │  HTF OHLCV (4h)  │
                └────────┬─────────┘
                         │ pivot detection
                         ▼
              ┌────────────────────┐
              │  S/R Level List    │
              │  (price, strength, │
              │   last_touch_ts)   │
              └────────┬───────────┘
                       │ timestamp mapping
                       ▼
┌──────────────┐   ┌──────────────────────┐
│ LTF Features │ + │ HTF S/R distances    │ ──► Range Strategy
│  (15m/30m)   │   │ (normalized by LTF   │     (unchanged logic)
│  rsi, atr,   │   │  ATR)                │
│  bb_pos ...  │   └──────────────────────┘
└──────────────┘
```

### Key Decision: ATR Normalization

S/R distances are normalized by **LTF ATR** (not HTF ATR):
- `sr_support_distance = (ltf_close - support_level_price) / ltf_atr`
- This ensures `sr_support_distance_max` parameter has consistent meaning regardless of
  which timeframe detected the level.

### Timestamp Mapping

For each LTF bar at timestamp T:
1. Find the most recent HTF bar whose close time ≤ T (no future leakage)
2. Use the set of active levels known at that HTF bar
3. Compute distances using LTF close and LTF ATR at bar T

### Level Management

Same as phase 5c but operating on HTF bars:
- `sr_pivot_left_bars` / `sr_pivot_right_bars`: window for swing detection (in HTF bars)
- `sr_cluster_atr_mult`: clustering distance (in HTF ATR units)
- `sr_max_levels`: max concurrent active levels
- `sr_level_max_age_bars`: expiry age (in HTF bars; e.g., 500 × 4h = 83 days)

### New Parameter

- `sr_htf_timeframe`: The higher timeframe for S/R detection.
  Default: `"4h"`. Options: `"1h"`, `"4h"`.
  Empty string means same-TF (backward compat with phase 5c behavior).

## Implementation

### engine.py

Add `compute_htf_sr_features()`:
- Inputs: HTF OHLCV arrays, LTF close/atr/timestamps, HTF timestamps, config params
- Logic: run existing `_detect_and_add_pivot()` on HTF, then for each LTF bar find
  active levels and compute LTF-normalized distances
- Output: dict with `sr_support_distance`, `sr_resistance_distance`, `sr_level_strength`

Add `overlay_htf_sr(features_df, htf_ohlcv_df, config)`:
- Replaces same-TF S/R columns with HTF-computed values
- Uses `pd.merge_asof` for timestamp alignment

### features/pipeline.py

- Add optional `htf_ohlcv_path` parameter
- If provided, call `overlay_htf_sr()` after `compute_features()`

### features/cli.py

- Add `--htf-ohlcv-path` argument
- Add `--sr-htf-timeframe` argument (for documentation/logging)

### timeframe_comparison.sh

- Support `4h` in `rule_map` for OHLCV resampling
- Generate HTF OHLCV file before feature computation
- Pass `--htf-ohlcv-path` to feature generation when `RANGE_SR_HTF_TIMEFRAME` is set

### core_expansion_tuning.sh

- Add `RANGE_SR_HTF_TIMEFRAME` env var (default: "4h")
- Optionally sweep: 1h vs 4h

### range_strategy.py

NO CHANGES — reads same columns, same logic. Only the quality of
`sr_support_distance` / `sr_level_strength` improves because levels
come from higher timeframe.

## Test Plan

1. Unit test: `compute_htf_sr_features()` with synthetic HTF/LTF data
2. Unit test: timestamp mapping correctness (no future leakage)
3. Integration: full pipeline with HTF OHLCV produces valid features
4. Autotune: sweep (1h, 4h) × sr_dist × sr_strength × entry_score

## Failure Modes

- HTF OHLCV not available → fallback to same-TF S/R (existing behavior)
- Too few HTF bars for pivot detection → NaN distances (strategy falls back)
- 4h levels too far from 15m price → larger `sr_support_distance_max` needed

## Expected Improvement Over Phase 5c

- Fewer detected levels → higher quality per level
- Less noise → fewer false entries
- Institutional-grade levels → better reversal probability
- Same exit logic (resistance exit) on more reliable levels
