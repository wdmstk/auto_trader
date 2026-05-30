from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.backtest.simulator import BacktestConfig, run_backtest


def run_backtest_pipeline(
    *,
    ohlcv_path: str | Path,
    signals_path: str | Path,
    ml_path: str | Path | None = None,
    output_dir: str | Path = "data/backtest",
    config: BacktestConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    ohlcv = pd.read_parquet(ohlcv_path)
    signals = pd.read_parquet(signals_path)
    ml_df = pd.read_parquet(ml_path) if ml_path else None
    trades, portfolio, metrics = run_backtest(
        ohlcv_df=ohlcv,
        signals_df=signals,
        ml_df=ml_df,
        config=config,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    trades.to_parquet(out / "trades.parquet", index=False)
    portfolio.to_parquet(out / "portfolio.parquet", index=False)
    pd.DataFrame([metrics]).to_parquet(out / "metrics.parquet", index=False)
    return trades, portfolio, metrics
