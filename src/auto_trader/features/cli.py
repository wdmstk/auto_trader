from __future__ import annotations

import argparse
from pathlib import Path

from auto_trader.features.engine import FeatureConfig
from auto_trader.features.pipeline import generate_and_save_features


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate features from OHLCV parquet.")
    parser.add_argument("--ohlcv-path", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--output-dir", default="data/features")
    parser.add_argument("--feature-version", default="v1")
    parser.add_argument("--min-history-bars", type=int, default=50)
    parser.add_argument("--htf-ohlcv-path", default=None,
                        help="Path to higher-timeframe OHLCV for S/R level detection")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = FeatureConfig(
        feature_version=args.feature_version,
        min_history_bars=args.min_history_bars,
    )
    features, saved_path = generate_and_save_features(
        ohlcv_path=Path(args.ohlcv_path),
        symbol=args.symbol,
        timeframe=args.timeframe,
        output_dir=Path(args.output_dir),
        config=cfg,
        htf_ohlcv_path=Path(args.htf_ohlcv_path) if args.htf_ohlcv_path else None,
    )
    print(f"saved={saved_path} rows={len(features)} feature_version={cfg.feature_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
