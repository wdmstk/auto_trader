from __future__ import annotations

import time
from pathlib import Path

from auto_trader.ops.alerts import AlertThresholds
from auto_trader.ops.pipeline import run_alert_pipeline


def run_alert_watch(
    *,
    runtime_state_path: str | Path = "data/runtime/control_state.json",
    risk_eval_path: str | Path = "data/risk/risk_eval.parquet",
    order_events_path: str | Path | None = None,
    output_dir: str | Path = "data/ops",
    thresholds: AlertThresholds | None = None,
    interval_sec: float = 5.0,
    max_iterations: int | None = None,
) -> int:
    iterations = 0
    while True:
        run_alert_pipeline(
            runtime_state_path=runtime_state_path,
            risk_eval_path=risk_eval_path,
            order_events_path=order_events_path,
            output_dir=output_dir,
            thresholds=thresholds,
        )
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            return iterations
        time.sleep(max(interval_sec, 0.1))
