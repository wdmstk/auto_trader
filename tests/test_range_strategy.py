from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import pandas as pd

from auto_trader.strategy.range_strategy import RangeStrategyConfig, generate_range_signals


def _build_inputs(
    *,
    include_new_features: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    feats: list[dict[str, object]] = []
    regimes: list[dict[str, object]] = []
    risks: list[dict[str, object]] = []
    for i in range(6):
        ts = base + timedelta(minutes=i)
        row: dict[str, object] = {
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "timestamp": ts,
            "rsi": 45.0 if i in (1, 2) else 60.0,
            "wick_ratio": 0.7 if i in (1, 2) else 0.2,
            "mean_reversion_distance": -0.5 if i in (1, 2) else 0.01,
            "reversal_candle_flag": 1 if i in (1, 2) else 0,
        }
        if include_new_features:
            row["bb_position"] = 0.1 if i in (1, 2) else 0.6
            row["volume_spike"] = 1 if i in (1, 2) else 0
            row["price_vs_recent_low"] = 0.5 if i in (1, 2) else 3.0
            row["atr"] = 100.0
        feats.append(row)
        regimes.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "regime": "RANGE" if i < 4 else "HIGH_VOL",
                "is_trade_allowed": i < 4,
                "confidence": 0.8,
            }
        )
        risks.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "risk_blocked": i == 2,
            }
        )
    return pd.DataFrame(feats), pd.DataFrame(regimes), pd.DataFrame(risks)


def test_entry_only_in_range_and_not_blocked() -> None:
    f, r, k = _build_inputs()
    out = generate_range_signals(features_df=f, regime_df=r, risk_df=k)
    # i=1 should pass entry rule, i=2 blocked by risk
    assert bool(out.loc[1, "entry_signal"]) is True
    assert bool(out.loc[2, "entry_signal"]) is False
    # high vol rows must be blocked
    assert bool(out.loc[4, "entry_signal"]) is False
    assert bool(out.loc[5, "entry_signal"]) is False


def test_reason_codes_present() -> None:
    f, r, k = _build_inputs()
    out = generate_range_signals(features_df=f, regime_df=r, risk_df=k)
    for codes in out["signal_reason_codes"]:
        assert isinstance(codes, list)
        assert len(codes) > 0


def test_high_vol_sets_block_reason() -> None:
    f, r, k = _build_inputs()
    out = generate_range_signals(features_df=f, regime_df=r, risk_df=k)
    codes = cast(list[str], out.loc[4, "signal_reason_codes"])
    assert "RG_BLOCK_HIGH_VOL" in codes


def test_entry_works_without_new_features() -> None:
    """Backward compatibility: entry works when new feature columns are absent."""
    f, r, k = _build_inputs(include_new_features=False)
    out = generate_range_signals(features_df=f, regime_df=r, risk_df=k)
    # With only RSI+wick+MR scoring (no bb_pos, vol_spike), score can still be enough
    # rsi_ok=1, wick_ok=1, mr_ok=1, bb_pos=1(default), vol=0, rev=1
    # score = (1+1+1.5+2+0+0.5)/7 = 6/7 ≈ 0.857 >= 0.6
    assert bool(out.loc[1, "entry_signal"]) is True


def test_range_reentry_cooldown_blocks_following_bar() -> None:
    f, r, k = _build_inputs()
    out = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(reentry_cooldown_bars=1),
    )
    assert bool(out.loc[1, "entry_signal"]) is True
    codes = cast(list[str], out.loc[2, "signal_reason_codes"])
    assert "RG_BLOCK_REENTRY_COOLDOWN" in codes


def test_range_enabled_symbols_blocks_non_target() -> None:
    f, r, k = _build_inputs()
    f["symbol"] = "ETHUSDT"
    r["symbol"] = "ETHUSDT"
    k["symbol"] = "ETHUSDT"
    out = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(enabled_symbols=("BTCUSDT",)),
    )
    assert bool(out["entry_signal"].any()) is False
    codes = cast(list[str], out.loc[1, "signal_reason_codes"])
    assert "RG_BLOCK_SYMBOL_DISABLED" in codes


def test_range_max_hold_bars_forces_exit() -> None:
    f, r, k = _build_inputs()
    out = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(max_hold_bars=1),
    )
    assert bool(out.loc[1, "entry_signal"]) is True
    assert bool(out.loc[3, "exit_signal"]) is True
    codes = cast(list[str], out.loc[3, "signal_reason_codes"])
    assert "RG_EXIT_MAX_HOLD" in codes


def test_min_entry_score_filters_effectively() -> None:
    """min_entry_score now actually filters entries (unlike old all-AND logic)."""
    f, r, k = _build_inputs()
    # With high score threshold, entry should be blocked
    out_high = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(min_entry_score=0.99),
    )
    # With low score threshold, entry should pass
    out_low = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(min_entry_score=0.5),
    )
    assert bool(out_low.loc[1, "entry_signal"]) is True
    # At 0.99 threshold, only perfect score passes
    # i=1 has all signals: rsi=1, wick=1, mr=1.5, bb_pos=2, vol=1, rev=0.5 = 7/7 = 1.0
    # so even 0.99 passes for the ideal case
    assert bool(out_high.loc[1, "entry_signal"]) is True

    # Now test with partial signals - remove volume spike
    f2 = f.copy()
    f2["volume_spike"] = 0
    out_partial_high = generate_range_signals(
        features_df=f2,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(min_entry_score=0.99),
    )
    out_partial_low = generate_range_signals(
        features_df=f2,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(min_entry_score=0.5),
    )
    # Without volume: (1+1+1.5+2+0+0.5)/7 = 6/7 ≈ 0.857 < 0.99
    assert bool(out_partial_high.loc[1, "entry_signal"]) is False
    assert bool(out_partial_low.loc[1, "entry_signal"]) is True


def test_bb_position_filters_entries() -> None:
    """Entries blocked when price is not in BB lower zone."""
    f, r, k = _build_inputs()
    f["bb_position"] = 0.8  # Above BB middle - not a good entry zone
    # bb_pos_ok = False, so score drops: (1+1+1.5+0+1+0.5)/7 = 5/7 ≈ 0.714
    # Still >= 0.6 default, but check with higher threshold
    out_strict = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(bb_position_max=0.35, min_entry_score=0.8),
    )
    assert bool(out_strict.loc[1, "entry_signal"]) is False


def test_volume_spike_contributes_to_score() -> None:
    """Volume spike adds to entry score."""
    f, r, k = _build_inputs()
    # Remove volume spike
    f["volume_spike"] = 0
    out_no_vol = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(min_entry_score=0.9),
    )
    # Add volume spike
    f["volume_spike"] = 1
    out_with_vol = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(min_entry_score=0.9),
    )
    # Without vol: 6/7 = 0.857 < 0.9, With vol: 7/7 = 1.0 >= 0.9
    assert bool(out_no_vol.loc[1, "entry_signal"]) is False
    assert bool(out_with_vol.loc[1, "entry_signal"]) is True
