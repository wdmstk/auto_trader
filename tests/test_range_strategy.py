from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from auto_trader.strategy.range_strategy import generate_range_signals


def _build_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    feats: list[dict[str, object]] = []
    regimes: list[dict[str, object]] = []
    risks: list[dict[str, object]] = []
    for i in range(6):
        ts = base + timedelta(minutes=i)
        feats.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "rsi": 45.0 if i in (1, 2) else 60.0,
                "wick_ratio": 0.7 if i in (1, 2) else 0.2,
                "mean_reversion_distance": -0.2 if i in (1, 2) else 0.01,
                "reversal_candle_flag": 1 if i in (1, 2) else 0,
            }
        )
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
    codes = out.loc[4, "signal_reason_codes"]
    assert "RG_BLOCK_HIGH_VOL" in codes
