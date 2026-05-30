from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.notify.channels import Notifier
from auto_trader.notify.models import AlertMessage, SendResult
from auto_trader.notify.pipeline import run_notification_pipeline


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


def test_run_notification_pipeline_saves_jsonl(tmp_path: Path) -> None:
    alerts_path = tmp_path / "alerts.parquet"
    pd.DataFrame(
        [
            {
                "alert_code": "RISK_DD_BREACH",
                "severity": "critical",
                "detected_at": "2026-01-01T00:00:00+00:00",
                "source": "risk",
                "summary": "dd breach",
                "action_required": "stop",
            }
        ]
    ).to_parquet(alerts_path, index=False)

    out_df, saved = run_notification_pipeline(
        alerts_path=alerts_path,
        notifiers=[DummyNotifier()],
        output_dir=tmp_path / "ops",
        state_path=tmp_path / "ops" / "notify_state.json",
    )
    assert len(out_df) == 1
    assert saved.exists()
    lines = saved.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
