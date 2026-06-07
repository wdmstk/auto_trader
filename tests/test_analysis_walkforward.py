from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.analysis.walkforward import WalkforwardConfig, run_walkforward_report


def test_walkforward_writes_closed_trade_artifact(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    market_rows = []
    signal_rows = []
    for idx in range(20):
        timestamp = base + timedelta(minutes=idx)
        market_rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": timestamp,
                "open": 100.0 + idx,
                "high": 101.0 + idx,
                "low": 99.0 + idx,
                "close": 100.0 + idx,
                "volume": 1000.0,
            }
        )
        signal_rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": timestamp,
                "entry_signal": idx in {2, 12},
                "exit_signal": idx in {5, 15},
                "pass_filter": True,
                "regime": "TREND",
            }
        )
    market_path = tmp_path / "market.parquet"
    signals_path = tmp_path / "signals.parquet"
    pd.DataFrame(market_rows).to_parquet(market_path)
    pd.DataFrame(signal_rows).to_parquet(signals_path)

    paths = run_walkforward_report(
        ohlcv_path=market_path,
        signals_path=signals_path,
        config=WalkforwardConfig(
            n_folds=2,
            strategy="trend",
            symbol="ETHUSDT",
            timeframe="1m",
            output_dir=tmp_path,
            delay_bars=0,
        ),
    )

    closed = pd.read_parquet(paths["closed_trades_path"])
    assert {"entry_ts", "exit_ts", "pnl", "entry_notional", "return_bps", "fold"}.issubset(
        closed.columns
    )
    assert len(closed) == 2
