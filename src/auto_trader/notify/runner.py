from __future__ import annotations

import time
from pathlib import Path

from auto_trader.notify.channels import Notifier
from auto_trader.notify.pipeline import run_notification_pipeline
from auto_trader.notify.service import NotifyPolicy


def run_notify_watch(
    *,
    alerts_path: str | Path = "data/ops/alerts.parquet",
    notifiers: list[Notifier],
    output_dir: str | Path = "data/ops",
    policy: NotifyPolicy | None = None,
    state_path: str | Path = "data/ops/notify_state.json",
    interval_sec: float = 5.0,
    max_iterations: int | None = None,
) -> int:
    iterations = 0
    while True:
        run_notification_pipeline(
            alerts_path=alerts_path,
            notifiers=notifiers,
            output_dir=output_dir,
            policy=policy,
            state_path=state_path,
        )
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            return iterations
        time.sleep(max(interval_sec, 0.1))
