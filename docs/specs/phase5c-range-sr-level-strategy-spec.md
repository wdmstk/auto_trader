# Phase 5c Spec: RANGE Strategy S/R Level Rewrite

- Version: 1.0
- Date: 2026-06-23
- Parent: phase5b-range-strategy-structural-improvement-spec.md

## Background

Phase 5b added weighted scoring + BB position awareness + volume spike confirmation.
After fixing the pipeline (PR #41), autotune results with 108 parameter combinations
still show PF < 1.0 across all routes. BB mean reversion lacks a structural edge:
BB bands measure volatility-relative position but do not identify price levels
where buy/sell orders concentrate.

## Goal

Replace BB-centric entry logic with horizontal Support/Resistance level-based
entry logic while preserving the weighted scoring framework and existing
regime/risk/exit infrastructure.

## Design

### 1. S/R Level Detection (features/engine.py)

Swing-based pivot detection with level clustering:

```
swing_low[i] = low[i] == min(low[i-left_bars : i+right_bars+1])
swing_high[i] = high[i] == max(high[i-left_bars : i+right_bars+1])
```

Parameters:
- `sr_pivot_left_bars: int = 5` (lookback for pivot confirmation)
- `sr_pivot_right_bars: int = 5` (lookahead for pivot confirmation)
- `sr_cluster_atr_mult: float = 0.5` (levels within 0.5*ATR are merged)
- `sr_max_levels: int = 10` (keep top N strongest levels)
- `sr_level_max_age_bars: int = 500` (expire old levels)

Level strength = number of touches (pivots clustered at same level).

Output features per bar:
- `sr_distance`: `min(|close - nearest_support|, |close - nearest_resistance|) / atr`
  Lower = closer to S/R level = better for range entry.
- `sr_support_distance`: `(close - nearest_support) / atr`
  Positive and small = price sitting just above support.
- `sr_level_strength`: touch count of the nearest level (higher = stronger)
- `sr_level_count`: number of active S/R levels within `sr_proximity_atr * ATR`

### 2. Entry Logic Change (range_strategy.py)

Replace `bb_position_ok` and `mr_ok` with S/R-based conditions:

```python
# S/R proximity: price is near a support level
sr_near_support = sr_support_distance <= cfg.sr_support_distance_max  # e.g. 1.5 ATR

# S/R level is strong enough
sr_strong = sr_level_strength >= cfg.sr_min_level_strength  # e.g. 2 touches

# New weighted score
score = (
    w_rsi * rsi_ok +
    w_wick * wick_ok +
    w_sr_proximity * sr_near_support +  # replaces w_mr
    w_sr_strength * sr_strong +          # replaces w_bb_pos
    w_vol * vol_ok +
    w_reversal_bonus * rev_ok
) / total_weight
```

Key change: entry requires proximity to a **real support level** with
confirmed touches, not just BB band position.

### 3. Exit Logic

Keep existing exits (MR neutral, regime change, max hold, ATR trail).
Add S/R-based exit:
- `sr_resistance_exit`: if in position and price approaches nearest resistance
  within `sr_resistance_exit_atr` * ATR, signal exit (take profit at resistance).

### 4. Config Changes

Remove BB-specific params, add S/R params:

```python
@dataclass(frozen=True)
class RangeStrategyConfig:
    # Existing (kept)
    rsi_min: float = 35.0
    rsi_max: float = 55.0
    wick_ratio_min: float = 0.3
    exit_mean_reversion_neutral_abs: float = 0.15
    default_position_size_ratio: float = 0.1
    require_reversal_candle: bool = False
    min_entry_score: float = 0.5
    reentry_cooldown_bars: int = 0
    max_hold_bars: int = 16
    enabled_symbols: tuple[str, ...] = ()
    volume_spike_threshold: float = 1.3
    exit_atr_trail_multiplier: float = 2.0

    # Removed: bb_position_max, w_bb_pos, w_mr,
    #          mean_reversion_distance_max, price_vs_recent_low_max

    # New: S/R parameters
    sr_support_distance_max: float = 1.5   # max ATR distance to support
    sr_min_level_strength: int = 2         # min touches for valid level
    sr_resistance_exit_atr: float = 0.5    # exit when this close to resistance

    # Updated weights
    w_rsi: float = 1.0
    w_wick: float = 1.0
    w_sr_proximity: float = 2.0    # replaces w_mr (S/R proximity most important)
    w_sr_strength: float = 1.5     # replaces w_bb_pos
    w_vol: float = 1.0
    w_reversal_bonus: float = 0.5
```

### 5. Backward Compatibility

- Feature engine adds new columns alongside existing ones (no removal)
- Old BB-related features remain computed (used by other analysis)
- Strategy config defaults change but CLI/autotune can override
- Graceful degradation: if S/R columns missing, fall back to neutral values

## Test Plan

- S/R feature computation: pivots detected at known swing points
- Level clustering: nearby pivots merge into single level
- Entry near support: entry triggers when price near strong support
- No entry far from support: entry blocked when far from all levels
- Resistance exit: position closed when approaching resistance
- Backward compat: strategy works when S/R columns absent
- Score filtering: different min_entry_score values give different results

## Failure Modes

- Too few S/R levels detected: relax pivot parameters or reduce min_strength
- All entries blocked: lower sr_support_distance_max or w_sr_proximity weight
- S/R levels too noisy: increase sr_pivot_left/right_bars for stronger pivots
