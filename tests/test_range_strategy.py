from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import pandas as pd

from auto_trader.strategy.range_strategy import RangeStrategyConfig, generate_range_signals


def _build_inputs(
    *,
    include_sr_features: bool = True,
    include_legacy_features: bool = True,
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
        if include_sr_features:
            row["sr_support_distance"] = 0.5 if i in (1, 2) else 5.0
            row["sr_resistance_distance"] = 3.0 if i in (1, 2) else 0.2
            row["sr_level_strength"] = 3.0 if i in (1, 2) else 0.0
            row["atr"] = 100.0
        if include_legacy_features:
            row["bb_position"] = 0.1 if i in (1, 2) else 0.6
            row["volume_spike"] = 1 if i in (1, 2) else 0
            row["price_vs_recent_low"] = 0.5 if i in (1, 2) else 3.0
            if "atr" not in row:
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


def test_entry_works_without_sr_features() -> None:
    """Backward compatibility: entry works when S/R feature columns are absent."""
    f, r, k = _build_inputs(include_sr_features=False, include_legacy_features=True)
    out = generate_range_signals(features_df=f, regime_df=r, risk_df=k)
    # Falls back to legacy BB scoring
    # rsi_ok=1, wick_ok=1, mr_ok=1(w=1.5), bb_pos_ok=1(w=2.0), vol_ok=1(w=1.0), rev_ok=1(w=0.5)
    # score = 7/7 = 1.0 >= 0.5
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


def test_sr_proximity_filters_entries() -> None:
    """Entries blocked when price is far from support level."""
    f, r, k = _build_inputs()
    # Make support distance very large -> sr_near_support = False
    f["sr_support_distance"] = 10.0
    # With strict threshold, entry should be blocked
    # rsi_ok=1(w=1), wick_ok=1(w=1), sr_prox=0(w=2), sr_str=1(w=1.5), vol=1(w=1), rev=1(w=0.5)
    # score = (1+1+0+1.5+1+0.5)/7 = 5/7 ≈ 0.714
    out_strict = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(sr_support_distance_max=1.5, min_entry_score=0.8),
    )
    assert bool(out_strict.loc[1, "entry_signal"]) is False


def test_sr_strength_filters_entries() -> None:
    """Entries blocked when S/R level is too weak."""
    f, r, k = _build_inputs()
    # Make strength 1 (below default min of 2)
    f["sr_level_strength"] = 1.0
    # rsi_ok=1(w=1), wick_ok=1(w=1), sr_prox=1(w=2), sr_str=0(w=1.5), vol=1(w=1), rev=1(w=0.5)
    # score = (1+1+2+0+1+0.5)/7 = 5.5/7 ≈ 0.786
    out = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(sr_min_level_strength=2, min_entry_score=0.9),
    )
    assert bool(out.loc[1, "entry_signal"]) is False

    # With lower threshold, should pass
    out_low = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(sr_min_level_strength=2, min_entry_score=0.5),
    )
    assert bool(out_low.loc[1, "entry_signal"]) is True


def test_sr_entry_has_reason_code() -> None:
    """Entry near S/R level includes the SR support reason code."""
    f, r, k = _build_inputs()
    out = generate_range_signals(features_df=f, regime_df=r, risk_df=k)
    codes = cast(list[str], out.loc[1, "signal_reason_codes"])
    assert "RG_ENTRY_SR_SUPPORT" in codes
    assert "RG_ENTRY_SCORE_OK" in codes


def test_sr_resistance_exit() -> None:
    """Position should exit when price approaches resistance level."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    feats: list[dict[str, object]] = []
    regimes: list[dict[str, object]] = []
    for i in range(5):
        ts = base + timedelta(minutes=i)
        feats.append({
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "timestamp": ts,
            "rsi": 45.0,
            "wick_ratio": 0.7,
            "mean_reversion_distance": -0.5,
            "reversal_candle_flag": 1,
            "sr_support_distance": 0.5,
            "sr_resistance_distance": 0.3 if i == 2 else 3.0,
            "sr_level_strength": 3.0,
            "volume_spike": 1,
            "atr": 100.0,
        })
        regimes.append({
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "timestamp": ts,
            "regime": "RANGE",
            "is_trade_allowed": True,
            "confidence": 0.8,
        })

    f = pd.DataFrame(feats)
    r = pd.DataFrame(regimes)
    out = generate_range_signals(
        features_df=f,
        regime_df=r,
        config=RangeStrategyConfig(
            sr_resistance_exit_atr=0.5,
            exit_mean_reversion_neutral_abs=0.01,
        ),
    )
    # i=0: entry (all conditions met, no position)
    assert bool(out.loc[0, "entry_signal"]) is True
    # i=2: resistance exit (sr_resistance_distance=0.3 <= 0.5)
    codes = cast(list[str], out.loc[2, "signal_reason_codes"])
    assert "RG_EXIT_SR_RESISTANCE" in codes


def test_min_entry_score_filters_with_sr() -> None:
    """min_entry_score effectively filters with S/R-based scoring."""
    f, r, k = _build_inputs()
    # Remove volume spike so score doesn't reach max
    f["volume_spike"] = 0
    # rsi_ok=1(w=1), wick_ok=1(w=1), sr_prox=1(w=2), sr_str=1(w=1.5), vol=0(w=1), rev=1(w=0.5)
    # score = (1+1+2+1.5+0+0.5)/7 = 6/7 ≈ 0.857
    out_high = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(min_entry_score=0.99),
    )
    out_low = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(min_entry_score=0.5),
    )
    assert bool(out_high.loc[1, "entry_signal"]) is False
    assert bool(out_low.loc[1, "entry_signal"]) is True


def test_legacy_bb_scoring_when_no_sr_columns() -> None:
    """When S/R columns are absent, falls back to BB-based scoring."""
    f, r, k = _build_inputs(include_sr_features=False, include_legacy_features=True)
    # bb_position=0.8 -> bb_pos_ok=False for default 0.35 threshold
    f["bb_position"] = 0.8
    # Legacy score: rsi=1(w=1), wick=1(w=1), mr=1(w=1.5), bb_pos=0(w=2), vol=1(w=1), rev=1(w=0.5)
    # = (1+1+1.5+0+1+0.5)/7 = 5/7 ≈ 0.714
    out = generate_range_signals(
        features_df=f,
        regime_df=r,
        risk_df=k,
        config=RangeStrategyConfig(min_entry_score=0.8),
    )
    assert bool(out.loc[1, "entry_signal"]) is False
