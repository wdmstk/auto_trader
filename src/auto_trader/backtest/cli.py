from __future__ import annotations

import argparse
from pathlib import Path

from auto_trader.backtest.pipeline import run_backtest_pipeline
from auto_trader.backtest.simulator import BacktestConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run backtesting pipeline.")
    p.add_argument("--ohlcv-path", required=True)
    p.add_argument("--signals-path", required=True)
    p.add_argument("--ml-path", default=None)
    p.add_argument("--output-dir", default="data/backtest")
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--slippage-rate", type=float, default=0.0005)
    p.add_argument("--spread-rate", type=float, default=0.0003)
    p.add_argument("--delay-bars", type=int, default=1)
    return p


def main() -> int:
    args = build_parser().parse_args()
    cfg = BacktestConfig(
        fee_rate=args.fee_rate,
        slippage_rate=args.slippage_rate,
        spread_rate=args.spread_rate,
        execution_delay_bars=args.delay_bars,
    )
    trades, portfolio, metrics = run_backtest_pipeline(
        ohlcv_path=Path(args.ohlcv_path),
        signals_path=Path(args.signals_path),
        ml_path=Path(args.ml_path) if args.ml_path else None,
        output_dir=Path(args.output_dir),
        config=cfg,
    )
    print(
        f"trades={len(trades)} bars={len(portfolio)} PF={metrics['PF']:.4f} "
        f"MaxDD={metrics['MaxDD']:.4f} MonthlyPnL={metrics['MonthlyPnL']:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
