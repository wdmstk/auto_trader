from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from auto_trader.strategy.trend_strategy import generate_trend_signals


def _build_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    feats: list[dict[str, object]] = []
    regimes: list[dict[str, object]] = []
    risks: list[dict[str, object]] = []
    pnls: list[dict[str, object]] = []
    for i in range(8):
        ts = base + timedelta(minutes=i)
        feats.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "breakout_persistence": 0.8 if i < 5 else 0.2,
                "momentum_persistence": 0.8 if i < 5 else 0.2,
                "pullback_shallowness": 0.7 if i < 5 else 0.1,
                "higher_high_persistence": 0.7 if i < 5 else 0.1,
                "trend_efficiency": 0.2 if i < 6 else 0.05,
            }
        )
        regimes.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "regime": "TREND" if i < 6 else "HIGH_VOL",
                "is_trade_allowed": i < 6,
                "confidence": 0.9,
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
        pnls.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "unrealized_pnl_pct": 0.03 if i in (1, 3, 4) else -0.01,
            }
        )
    return pd.DataFrame(feats), pd.DataFrame(regimes), pd.DataFrame(risks), pd.DataFrame(pnls)


def test_trend_entry_only_when_gate_open() -> None:
    f, r, k, p = _build_inputs()
    out = generate_trend_signals(features_df=f, regime_df=r, risk_df=k, pnl_df=p)
    assert bool(out.loc[0, "entry_signal"]) is True
    assert bool(out.loc[2, "entry_signal"]) is False  # risk blocked
    assert bool(out.loc[6, "entry_signal"]) is False  # high vol


def test_high_vol_blocks_add_and_entry() -> None:
    f, r, k, p = _build_inputs()
    out = generate_trend_signals(features_df=f, regime_df=r, risk_df=k, pnl_df=p)
    for idx in [6, 7]:
        assert bool(out.loc[idx, "entry_signal"]) is False
        assert bool(out.loc[idx, "add_signal"]) is False
        assert "TR_BLOCK_HIGH_VOL" in out.loc[idx, "signal_reason_codes"]


def test_reason_codes_exist() -> None:
    f, r, k, p = _build_inputs()
    out = generate_trend_signals(features_df=f, regime_df=r, risk_df=k, pnl_df=p)
    for codes in out["signal_reason_codes"]:
        assert isinstance(codes, list)
        assert len(codes) > 0
