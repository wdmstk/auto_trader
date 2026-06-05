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
    assert "ExpectancyBps" in metrics
    assert "TotalCostEst" in metrics


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
        & (
            pd.to_datetime(trades["timestamp"], utc=True)
            >= pd.to_datetime(str(ohlcv.loc[5, "timestamp"]), utc=True)
        )
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
    assert "PeriodPnL" in metrics
    assert float(metrics["TotalCostEst"]) >= 0.0


def test_limit_mode_emits_order_status_rows() -> None:
    ohlcv, signals, ml = _sample_inputs()
    # Force a touch-only scenario on entry and exit to exercise partial/canceled.
    ohlcv.loc[2, "high"] = 102.2
    ohlcv.loc[2, "low"] = 101.8
    ohlcv.loc[3, "high"] = 103.5
    ohlcv.loc[3, "low"] = 103.2
    trades, _, metrics = run_backtest(
        ohlcv_df=ohlcv,
        signals_df=signals,
        ml_df=ml,
        config=BacktestConfig(
            execution_delay_bars=1,
            order_mode="limit",
            limit_offset_rate=0.0,
            limit_partial_fill_ratio=0.1,
        ),
    )
    assert "order_mode" in trades.columns
    assert (trades["order_mode"] == "limit").all()
    assert set(trades["status"]).issubset({"filled", "partial", "expired", "canceled"})
    assert "LimitOrderCount" in metrics
    assert "LimitTakerLikeRate" in metrics


def test_fee_split_for_market_and_limit() -> None:
    ohlcv, signals, ml = _sample_inputs()
    market_trades, _, _ = run_backtest(
        ohlcv_df=ohlcv,
        signals_df=signals,
        ml_df=ml,
        config=BacktestConfig(
            execution_delay_bars=0,
            order_mode="market",
            taker_fee_rate=0.001,
            maker_fee_rate=0.0,
        ),
    )
    limit_trades, _, _ = run_backtest(
        ohlcv_df=ohlcv,
        signals_df=signals,
        ml_df=ml,
        config=BacktestConfig(
            execution_delay_bars=0,
            order_mode="limit",
            taker_fee_rate=0.001,
            maker_fee_rate=0.0001,
            limit_offset_rate=0.0,
        ),
    )
    assert float(market_trades["fee"].sum()) > 0.0
    assert float(limit_trades["fee"].sum()) >= 0.0


def test_limit_depth_queue_model_reduces_partial_fill() -> None:
    ohlcv, signals, ml = _sample_inputs()
    ohlcv.loc[2, "high"] = 102.2
    ohlcv.loc[2, "low"] = 101.8
    ohlcv.loc[3, "high"] = 103.5
    ohlcv.loc[3, "low"] = 103.2
    ohlcv.loc[2, "volume"] = 1.0

    trades, _, _ = run_backtest(
        ohlcv_df=ohlcv,
        signals_df=signals,
        ml_df=ml,
        config=BacktestConfig(
            execution_delay_bars=1,
            order_mode="limit",
            limit_offset_rate=0.0,
            limit_partial_fill_ratio=0.5,
            limit_book_depth_units=0.2,
            limit_queue_ahead_units=0.1,
            limit_volume_participation_rate=1.0,
        ),
    )
    partials = trades[trades["status"] == "partial"]
    assert not partials.empty
    assert float(partials.iloc[0]["size"]) == 0.1


def test_limit_depth_queue_model_keeps_legacy_behavior_by_default() -> None:
    ohlcv, signals, ml = _sample_inputs()
    ohlcv.loc[2, "high"] = 102.2
    ohlcv.loc[2, "low"] = 101.8
    ohlcv.loc[3, "high"] = 103.5
    ohlcv.loc[3, "low"] = 103.2

    trades, _, _ = run_backtest(
        ohlcv_df=ohlcv,
        signals_df=signals,
        ml_df=ml,
        config=BacktestConfig(
            execution_delay_bars=1,
            order_mode="limit",
            limit_offset_rate=0.0,
            limit_partial_fill_ratio=0.2,
        ),
    )
    partials = trades[trades["status"] == "partial"]
    assert not partials.empty
    assert float(partials.iloc[0]["size"]) == 0.2
