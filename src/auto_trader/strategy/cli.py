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
    p.add_argument("--drift-report-path", default=None)
    p.add_argument("--ml-artifact-path", default=None)
    p.add_argument("--allowed-hours", default="")
    p.add_argument("--range-rsi-min", type=float, default=40.0)
    p.add_argument("--range-rsi-max", type=float, default=50.0)
    p.add_argument("--range-wick-ratio-min", type=float, default=0.5)
    p.add_argument("--range-mean-reversion-distance-max", type=float, default=-0.1)
    p.add_argument("--range-exit-mean-reversion-neutral-abs", type=float, default=0.05)
    p.add_argument("--range-default-position-size-ratio", type=float, default=0.1)
    p.add_argument("--range-require-reversal-candle", default="true", choices=["true", "false"])
    p.add_argument("--range-min-entry-score", type=float, default=1.0)
    p.add_argument("--range-reentry-cooldown-bars", type=int, default=0)
    p.add_argument("--range-max-hold-bars", type=int, default=0)
    p.add_argument("--range-enabled-symbols", default="")
    p.add_argument("--trend-min-entry-score", type=float, default=1.0)
    p.add_argument("--trend-breakout-persistence-min", type=float, default=0.6)
    p.add_argument("--trend-momentum-persistence-min", type=float, default=0.5)
    p.add_argument("--trend-pullback-shallowness-min", type=float, default=0.5)
    p.add_argument("--trend-higher-high-persistence-min", type=float, default=0.5)
    p.add_argument("--trend-efficiency-exit-threshold", type=float, default=0.1)
    p.add_argument("--trend-reentry-cooldown-bars", type=int, default=0)
    p.add_argument("--trend-max-hold-bars", type=int, default=0)
    p.add_argument("--trend-enabled-symbols", default="")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.strategy == "range":
        require_reversal = str(args.range_require_reversal_candle).lower() == "true"
        range_enabled_symbols = tuple(
            x.strip() for x in str(args.range_enabled_symbols).split(",") if x.strip()
        )
        signals, saved = build_and_save_range_signals(
            features_path=Path(args.features_path),
            regime_path=Path(args.regime_path),
            symbol=args.symbol,
            timeframe=args.timeframe,
            output_dir=Path(args.output_dir),
            risk_path=Path(args.risk_path) if args.risk_path else None,
            drift_report_path=Path(args.drift_report_path) if args.drift_report_path else None,
            ml_artifact_path=Path(args.ml_artifact_path) if args.ml_artifact_path else None,
            allowed_hours=str(args.allowed_hours).strip() or None,
            config=RangeStrategyConfig(
                rsi_min=args.range_rsi_min,
                rsi_max=args.range_rsi_max,
                wick_ratio_min=args.range_wick_ratio_min,
                mean_reversion_distance_max=args.range_mean_reversion_distance_max,
                exit_mean_reversion_neutral_abs=args.range_exit_mean_reversion_neutral_abs,
                default_position_size_ratio=args.range_default_position_size_ratio,
                require_reversal_candle=require_reversal,
                min_entry_score=args.range_min_entry_score,
                reentry_cooldown_bars=args.range_reentry_cooldown_bars,
                max_hold_bars=args.range_max_hold_bars,
                enabled_symbols=range_enabled_symbols,
            ),
        )
    else:
        trend_enabled_symbols = tuple(
            x.strip() for x in str(args.trend_enabled_symbols).split(",") if x.strip()
        )
        signals, saved = build_and_save_trend_signals(
            features_path=Path(args.features_path),
            regime_path=Path(args.regime_path),
            symbol=args.symbol,
            timeframe=args.timeframe,
            output_dir=Path(args.output_dir),
            risk_path=Path(args.risk_path) if args.risk_path else None,
            pnl_path=Path(args.pnl_path) if args.pnl_path else None,
            drift_report_path=Path(args.drift_report_path) if args.drift_report_path else None,
            ml_artifact_path=Path(args.ml_artifact_path) if args.ml_artifact_path else None,
            allowed_hours=str(args.allowed_hours).strip() or None,
            config=TrendStrategyConfig(
                min_entry_score=args.trend_min_entry_score,
                breakout_persistence_min=args.trend_breakout_persistence_min,
                momentum_persistence_min=args.trend_momentum_persistence_min,
                pullback_shallowness_min=args.trend_pullback_shallowness_min,
                higher_high_persistence_min=args.trend_higher_high_persistence_min,
                trend_efficiency_exit_threshold=args.trend_efficiency_exit_threshold,
                reentry_cooldown_bars=args.trend_reentry_cooldown_bars,
                max_hold_bars=args.trend_max_hold_bars,
                enabled_symbols=trend_enabled_symbols,
            ),
        )
    print(f"saved={saved} rows={len(signals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
