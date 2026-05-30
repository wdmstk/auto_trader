from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from auto_trader.backtest.simulator import BacktestConfig, run_backtest


def _sample_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    ohlcv_rows: list[dict[str, object]] = []
    signal_rows: list[dict[str, object]] = []
    ml_rows: list[dict[str, object]] = []

    prices = [100, 101, 102, 101, 103, 104]
    for i, p in enumerate(prices):
        ts = base + timedelta(minutes=i)
        ohlcv_rows.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "open": p,
                "high": p + 0.5,
                "low": p - 0.5,
                "close": p,
                "volume": 1000 + i,
            }
        )
        signal_rows.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "entry_signal": i == 1,
                "exit_signal": i == 4,
                "regime": "RANGE" if i < 5 else "HIGH_VOL",
            }
        )
        ml_rows.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "pass_filter": i != 2,
            }
        )
    return pd.DataFrame(ohlcv_rows), pd.DataFrame(signal_rows), pd.DataFrame(ml_rows)


def test_cost_and_filter_are_applied() -> None:
    ohlcv, signals, ml = _sample_inputs()
    trades, _, metrics = run_backtest(
        ohlcv_df=ohlcv,
        signals_df=signals,
        ml_df=ml,
        config=BacktestConfig(execution_delay_bars=1),
    )
    assert not trades.empty
    assert "fee" in trades.columns
    assert "slippage" in trades.columns
    assert "spread" in trades.columns
    assert "PF" in metrics


def test_high_vol_blocks_new_entry() -> None:
    ohlcv, signals, ml = _sample_inputs()
    signals.loc[5, "entry_signal"] = True
    trades, _, _ = run_backtest(
        ohlcv_df=ohlcv,
        signals_df=signals,
        ml_df=ml,
        config=BacktestConfig(execution_delay_bars=0),
    )
    entry_after_hv = trades[
        (trades["side"] == "buy")
        & (pd.to_datetime(trades["timestamp"], utc=True) >= pd.Timestamp(ohlcv.loc[5, "timestamp"]))
    ]
    assert entry_after_hv.empty


def test_maxdd_is_computable() -> None:
    ohlcv, signals, ml = _sample_inputs()
    _, portfolio, metrics = run_backtest(
        ohlcv_df=ohlcv,
        signals_df=signals,
        ml_df=ml,
        config=BacktestConfig(execution_delay_bars=0),
    )
    assert not portfolio.empty
    assert 0.0 <= float(metrics["MaxDD"]) <= 1.0
