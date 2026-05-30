from __future__ import annotations

import argparse
from pathlib import Path

from auto_trader.backtest.simulator import BacktestConfig
from auto_trader.stress.pipeline import run_stress_tests
from auto_trader.stress.scenarios import StressScenarioConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run stress testing scenarios.")
    p.add_argument("--ohlcv-path", required=True)
    p.add_argument("--signals-path", required=True)
    p.add_argument("--ml-path", default=None)
    p.add_argument("--output-dir", default="data/stress")
    return p


def main() -> int:
    args = build_parser().parse_args()
    results, compare = run_stress_tests(
        ohlcv_path=Path(args.ohlcv_path),
        signals_path=Path(args.signals_path),
        ml_path=Path(args.ml_path) if args.ml_path else None,
        backtest_cfg=BacktestConfig(),
        stress_cfg=StressScenarioConfig(),
    )
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results.to_parquet(out / "stress_results.parquet", index=False)
    compare.to_parquet(out / "stress_degradation.parquet", index=False)
    print(f"scenarios={len(results)} compare_rows={len(compare)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
