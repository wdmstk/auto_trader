from __future__ import annotations

import argparse
from pathlib import Path

from auto_trader.strategy.pipeline import build_and_save_range_signals
from auto_trader.strategy.range_strategy import RangeStrategyConfig
from auto_trader.strategy.trend_pipeline import build_and_save_trend_signals
from auto_trader.strategy.trend_strategy import TrendStrategyConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build strategy signals.")
    p.add_argument("--strategy", choices=["range", "trend"], default="range")
    p.add_argument("--features-path", required=True)
    p.add_argument("--regime-path", required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--timeframe", required=True)
    p.add_argument("--output-dir", default="data/signals")
    p.add_argument("--risk-path", default=None)
    p.add_argument("--pnl-path", default=None)
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.strategy == "range":
        signals, saved = build_and_save_range_signals(
            features_path=Path(args.features_path),
            regime_path=Path(args.regime_path),
            symbol=args.symbol,
            timeframe=args.timeframe,
            output_dir=Path(args.output_dir),
            risk_path=Path(args.risk_path) if args.risk_path else None,
            config=RangeStrategyConfig(),
        )
    else:
        signals, saved = build_and_save_trend_signals(
            features_path=Path(args.features_path),
            regime_path=Path(args.regime_path),
            symbol=args.symbol,
            timeframe=args.timeframe,
            output_dir=Path(args.output_dir),
            risk_path=Path(args.risk_path) if args.risk_path else None,
            pnl_path=Path(args.pnl_path) if args.pnl_path else None,
            config=TrendStrategyConfig(),
        )
    print(f"saved={saved} rows={len(signals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
