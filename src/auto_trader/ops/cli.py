from __future__ import annotations

import argparse
import json
from pathlib import Path

from auto_trader.ops.alerts import AlertThresholds, evaluate_alerts


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Evaluate operations alerts.")
    p.add_argument("--runtime-state-path", default="data/runtime/control_state.json")
    p.add_argument("--risk-eval-path", default="data/risk/risk_eval.parquet")
    p.add_argument("--order-events-path", default=None)
    p.add_argument("--max-dd-pct", type=float, default=15.0)
    return p


def main() -> int:
    args = _build_parser().parse_args()
    alerts = evaluate_alerts(
        runtime_state_path=Path(args.runtime_state_path),
        risk_eval_path=Path(args.risk_eval_path),
        order_events_path=Path(args.order_events_path) if args.order_events_path else None,
        thresholds=AlertThresholds(max_dd_pct=float(args.max_dd_pct)),
    )
    print(json.dumps({"count": len(alerts), "alerts": alerts}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
