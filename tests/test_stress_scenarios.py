from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from auto_trader.stress.scenarios import apply_scenario


def _sample() -> tuple[pd.DataFrame, pd.DataFrame]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    o_rows: list[dict[str, object]] = []
    s_rows: list[dict[str, object]] = []
    for i in range(20):
        ts = base + timedelta(minutes=i)
        px = 100 + i * 0.1
        o_rows.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "open": px,
                "high": px + 0.3,
                "low": px - 0.3,
                "close": px,
                "volume": 1000 + i,
            }
        )
        s_rows.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "entry_signal": True,
                "exit_signal": False,
                "regime": "RANGE",
            }
        )
    return pd.DataFrame(o_rows), pd.DataFrame(s_rows)


def test_volatility_2x_changes_range() -> None:
    ohlcv, sig = _sample()
    out_o, _, failures = apply_scenario(ohlcv, sig, "volatility_2x")
    base_rng = (ohlcv["high"] - ohlcv["low"]).mean()
    out_rng = (out_o["high"] - out_o["low"]).mean()
    assert out_rng > base_rng
    assert failures == 0


def test_api_timeout_increases_failures() -> None:
    ohlcv, sig = _sample()
    _, out_s, failures = apply_scenario(ohlcv, sig, "api_timeout")
    assert failures > 0
    assert out_s["entry_signal"].sum() < sig["entry_signal"].sum()
