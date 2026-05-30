from __future__ import annotations

import argparse
import json
from pathlib import Path

from auto_trader.ops.alerts import AlertThresholds, evaluate_alerts
from auto_trader.ops.pipeline import run_alert_pipeline
from auto_trader.ops.runner import run_alert_watch


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Evaluate operations alerts.")
    p.add_argument("--runtime-state-path", default="data/runtime/control_state.json")
    p.add_argument("--risk-eval-path", default="data/risk/risk_eval.parquet")
    p.add_argument("--order-events-path", default=None)
    p.add_argument("--output-dir", default=None)
    p.add_argument("--max-dd-pct", type=float, default=15.0)
    p.add_argument("--watch", action="store_true")
    p.add_argument("--interval-sec", type=float, default=5.0)
    p.add_argument("--max-iterations", type=int, default=None)
    return p


def main() -> int:
    args = _build_parser().parse_args()
    thresholds = AlertThresholds(max_dd_pct=float(args.max_dd_pct))

    if args.watch:
        count = run_alert_watch(
            runtime_state_path=Path(args.runtime_state_path),
            risk_eval_path=Path(args.risk_eval_path),
            order_events_path=Path(args.order_events_path) if args.order_events_path else None,
            output_dir=Path(args.output_dir or "data/ops"),
            thresholds=thresholds,
            interval_sec=float(args.interval_sec),
            max_iterations=args.max_iterations,
        )
        print(json.dumps({"watch": True, "iterations": count}, ensure_ascii=True))
        return 0

    if args.output_dir:
        out, parquet_path, jsonl_path = run_alert_pipeline(
            runtime_state_path=Path(args.runtime_state_path),
            risk_eval_path=Path(args.risk_eval_path),
            order_events_path=Path(args.order_events_path) if args.order_events_path else None,
            output_dir=Path(args.output_dir),
            thresholds=thresholds,
        )
        print(
            json.dumps(
                {
                    "count": len(out),
                    "parquet_path": str(parquet_path),
                    "jsonl_path": str(jsonl_path),
                },
                ensure_ascii=True,
            )
        )
        return 0

    alerts = evaluate_alerts(
        runtime_state_path=Path(args.runtime_state_path),
        risk_eval_path=Path(args.risk_eval_path),
        order_events_path=Path(args.order_events_path) if args.order_events_path else None,
        thresholds=thresholds,
    )
    print(json.dumps({"count": len(alerts), "alerts": alerts}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
