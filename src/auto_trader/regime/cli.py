from __future__ import annotations

import argparse
from pathlib import Path

from auto_trader.regime.classifier import RegimeConfig
from auto_trader.regime.pipeline import classify_and_save_regime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify market regime from feature parquet.")
    parser.add_argument("--feature-path", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--output-dir", default="data/regime")
    parser.add_argument("--trend-adx-threshold", type=float, default=25.0)
    parser.add_argument("--trend-breakout-persistence-min-bars", type=int, default=3)
    parser.add_argument("--range-bb-width-percentile-max", type=float, default=40.0)
    parser.add_argument("--range-adx-max", type=float, default=20.0)
    parser.add_argument("--min-regime-hold-bars", type=int, default=3)
    parser.add_argument("--high-vol-cooldown-bars", type=int, default=5)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    cfg = RegimeConfig(
        trend_adx_threshold=args.trend_adx_threshold,
        trend_breakout_persistence_min_bars=args.trend_breakout_persistence_min_bars,
        range_bb_width_percentile_max=args.range_bb_width_percentile_max,
        range_adx_max=args.range_adx_max,
        min_regime_hold_bars=args.min_regime_hold_bars,
        high_vol_cooldown_bars=args.high_vol_cooldown_bars,
    )
    regime_df, saved_path = classify_and_save_regime(
        feature_path=Path(args.feature_path),
        symbol=args.symbol,
        timeframe=args.timeframe,
        output_dir=Path(args.output_dir),
        config=cfg,
    )
    print(f"saved={saved_path} rows={len(regime_df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
