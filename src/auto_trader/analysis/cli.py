from __future__ import annotations

import argparse
import json
from pathlib import Path

from auto_trader.analysis.walkforward import WalkforwardConfig, run_walkforward_report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run walkforward visual report generation.")
    p.add_argument("--ohlcv-path", required=True)
    p.add_argument("--signals-path", required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--timeframe", required=True)
    p.add_argument("--strategy", choices=["range", "trend"], required=True)
    p.add_argument("--folds", type=int, default=4)
    p.add_argument("--output-dir", default="data/analysis")
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--slippage-rate", type=float, default=0.0005)
    p.add_argument("--spread-rate", type=float, default=0.0003)
    p.add_argument("--delay-bars", type=int, default=1)
    p.add_argument("--order-mode", choices=["market", "limit"], default="market")
    p.add_argument("--maker-fee-rate", type=float, default=0.0)
    p.add_argument("--taker-fee-rate", type=float, default=0.0)
    p.add_argument("--limit-offset-rate", type=float, default=0.0)
    p.add_argument("--limit-partial-fill-ratio", type=float, default=0.1)
    return p


def main() -> int:
    args = build_parser().parse_args()
    out = run_walkforward_report(
        ohlcv_path=Path(args.ohlcv_path),
        signals_path=Path(args.signals_path),
        config=WalkforwardConfig(
            n_folds=args.folds,
            strategy=args.strategy,
            symbol=args.symbol,
            timeframe=args.timeframe,
            output_dir=Path(args.output_dir),
            fee_rate=args.fee_rate,
            slippage_rate=args.slippage_rate,
            spread_rate=args.spread_rate,
            delay_bars=args.delay_bars,
            order_mode=args.order_mode,
            maker_fee_rate=args.maker_fee_rate,
            taker_fee_rate=args.taker_fee_rate,
            limit_offset_rate=args.limit_offset_rate,
            limit_partial_fill_ratio=args.limit_partial_fill_ratio,
        ),
    )
    print(json.dumps(out, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
