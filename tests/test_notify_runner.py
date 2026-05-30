from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.notify.channels import Notifier
from auto_trader.notify.models import AlertMessage, SendResult
from auto_trader.notify.runner import run_notify_watch


class DummyNotifier(Notifier):
    channel_name = "webhook"

    def send(self, alert: AlertMessage) -> SendResult:
        return SendResult(
            channel=self.channel_name,
            alert_code=alert.alert_code,
            sent_at=alert.detected_at,
            success=True,
            response_code=200,
            error_reason="",
        )


def test_run_notify_watch(tmp_path: Path) -> None:
    alerts_path = tmp_path / "alerts.parquet"
    pd.DataFrame(
        [
            {
                "alert_code": "TEST_ALERT",
                "severity": "critical",
                "detected_at": "2026-01-01T00:00:00+00:00",
                "source": "test",
                "summary": "notify watch",
                "action_required": "check",
            }
        ]
    ).to_parquet(alerts_path, index=False)
    count = run_notify_watch(
        alerts_path=alerts_path,
        notifiers=[DummyNotifier()],
        output_dir=tmp_path / "ops",
        state_path=tmp_path / "ops" / "state.json",
        interval_sec=0.1,
        max_iterations=1,
    )
    assert count == 1
    assert (tmp_path / "ops" / "notifications.jsonl").exists()
