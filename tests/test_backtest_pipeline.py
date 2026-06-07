from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.backtest.pipeline import run_backtest_pipeline


def test_backtest_pipeline_outputs_artifacts(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    ohlcv_rows: list[dict[str, object]] = []
    signal_rows: list[dict[str, object]] = []
    ml_rows: list[dict[str, object]] = []
    for i in range(20):
        ts = base + timedelta(minutes=i)
        px = 100 + i * 0.2
        ohlcv_rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "open": px,
                "high": px + 0.5,
                "low": px - 0.5,
                "close": px,
                "volume": 500 + i,
            }
        )
        signal_rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "entry_signal": i == 2,
                "exit_signal": i == 10,
                "regime": "RANGE",
            }
        )
        ml_rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "pass_filter": True,
            }
        )

    ohlcv_path = tmp_path / "ohlcv.parquet"
    sig_path = tmp_path / "ETHUSDT_1m_trend_signals.parquet"
    ml_path = tmp_path / "ml.parquet"
    pd.DataFrame(ohlcv_rows).to_parquet(ohlcv_path, index=False)
    pd.DataFrame(signal_rows).to_parquet(sig_path, index=False)
    pd.DataFrame(ml_rows).to_parquet(ml_path, index=False)

    trades, portfolio, metrics = run_backtest_pipeline(
        ohlcv_path=ohlcv_path,
        signals_path=sig_path,
        ml_path=ml_path,
        output_dir=tmp_path / "backtest",
    )
    assert Path(tmp_path / "backtest" / "trades.parquet").exists()
    assert Path(tmp_path / "backtest" / "portfolio.parquet").exists()
    assert Path(tmp_path / "backtest" / "metrics.parquet").exists()
    metadata = Path(tmp_path / "backtest" / "metadata.json")
    assert metadata.exists()
    payload = pd.read_json(metadata, typ="series")
    assert payload["symbol"] == "ETHUSDT"
    assert payload["timeframe"] == "1m"
    assert payload["strategy"] == "trend"
    assert "PF" in metrics
    assert "Expectancy" in metrics
    assert "ExpectancyBps" in metrics
    assert "PeriodPnL" in metrics
    assert "TotalCostEst" in metrics
    assert len(portfolio) == 20
    assert len(trades) >= 2
