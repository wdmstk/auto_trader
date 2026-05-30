from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from auto_trader.ops.alerts import AlertThresholds, evaluate_alerts
from auto_trader.ops.store import AlertStore


def run_alert_pipeline(
    *,
    runtime_state_path: str | Path,
    risk_eval_path: str | Path,
    order_events_path: str | Path | None = None,
    output_dir: str | Path = "data/ops",
    thresholds: AlertThresholds | None = None,
    now: datetime | None = None,
) -> tuple[pd.DataFrame, Path, Path]:
    alerts = evaluate_alerts(
        runtime_state_path=runtime_state_path,
        risk_eval_path=risk_eval_path,
        order_events_path=order_events_path,
        thresholds=thresholds,
        now=now,
    )
    out = pd.DataFrame(alerts)
    store = AlertStore(output_dir)
    parquet_path, jsonl_path = store.save(out)
    return out, parquet_path, jsonl_path
