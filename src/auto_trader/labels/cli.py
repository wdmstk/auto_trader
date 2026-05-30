from __future__ import annotations

import argparse
from pathlib import Path

from auto_trader.labels.generator import LabelConfig
from auto_trader.labels.pipeline import generate_and_save_labels


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate TP/SL binary labels from OHLCV parquet.")
    parser.add_argument("--ohlcv-path", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--output-dir", default="data/labels")
    parser.add_argument("--features-path", default=None)
    parser.add_argument("--tp-pct", type=float, default=0.04)
    parser.add_argument("--sl-pct", type=float, default=0.02)
    parser.add_argument("--max-horizon-bars", type=int, default=120)
    parser.add_argument("--label-version", default="v1")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    cfg = LabelConfig(
        tp_pct=args.tp_pct,
        sl_pct=args.sl_pct,
        max_horizon_bars=args.max_horizon_bars,
        label_version=args.label_version,
    )
    labels, saved_path = generate_and_save_labels(
        ohlcv_path=Path(args.ohlcv_path),
        symbol=args.symbol,
        timeframe=args.timeframe,
        output_dir=Path(args.output_dir),
        config=cfg,
        features_path=Path(args.features_path) if args.features_path else None,
    )
    print(f"saved={saved_path} rows={len(labels)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
