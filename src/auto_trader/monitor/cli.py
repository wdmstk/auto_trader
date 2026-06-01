from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from auto_trader.monitor.metrics import collect_runtime_metrics


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Collect runtime/latency/backlog metrics.")
    p.add_argument("--runtime-state-path", default="data/runtime/control_state.json")
    p.add_argument("--gateway-state-path", default="data/exchange/gateway_state.json")
    p.add_argument("--risk-eval-path", default="data/risk/risk_eval.parquet")
    p.add_argument("--order-events-path", default="data/exchange/order_events.jsonl")
    p.add_argument("--output-jsonl", default=None)
    p.add_argument("--watch", action="store_true")
    p.add_argument("--interval-sec", type=float, default=5.0)
    p.add_argument("--max-iterations", type=int, default=None)
    return p


def _append_jsonl(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")


def main() -> int:
    args = _build_parser().parse_args()
    output_jsonl = Path(args.output_jsonl) if args.output_jsonl else None

    iterations = 0
    while True:
        row = collect_runtime_metrics(
            runtime_state_path=args.runtime_state_path,
            gateway_state_path=args.gateway_state_path,
            risk_eval_path=args.risk_eval_path,
            order_events_path=args.order_events_path,
        )
        if output_jsonl is not None:
            _append_jsonl(output_jsonl, row)
        print(json.dumps(row, ensure_ascii=True))

        iterations += 1
        if not args.watch:
            return 0
        if args.max_iterations is not None and iterations >= args.max_iterations:
            return 0
        time.sleep(max(float(args.interval_sec), 0.1))


if __name__ == "__main__":
    raise SystemExit(main())
