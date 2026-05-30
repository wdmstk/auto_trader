from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from auto_trader.notify.channels import Notifier
from auto_trader.notify.models import AlertMessage, SendResult
from auto_trader.notify.service import NotificationService, NotifyPolicy


@dataclass
class DummyNotifier(Notifier):
    channel_name: str
    ok: bool = True

    def send(self, alert: AlertMessage) -> SendResult:
        return SendResult(
            channel=self.channel_name,
            alert_code=alert.alert_code,
            sent_at=alert.detected_at,
            success=self.ok,
            response_code=200 if self.ok else 500,
            error_reason="" if self.ok else "send_failed",
        )


def _alert(severity: str) -> dict[str, str]:
    return {
        "alert_code": "RISK_DD_BREACH",
        "severity": severity,
        "detected_at": "2026-01-01T00:00:00+00:00",
        "source": "risk",
        "summary": "dd breach",
        "action_required": "stop",
    }


def test_critical_sent_to_all_channels(tmp_path: Path) -> None:
    notifiers: list[Notifier] = [
        DummyNotifier("slack"),
        DummyNotifier("email"),
        DummyNotifier("webhook"),
    ]
    svc = NotificationService(notifiers=notifiers, state_path=tmp_path / "state.json")
    out = svc.dispatch([_alert("critical")])
    assert len(out) == 3
    assert {str(r["channel"]) for r in out} == {"slack", "email", "webhook"}


def test_warning_respects_channel_policy(tmp_path: Path) -> None:
    notifiers: list[Notifier] = [
        DummyNotifier("slack"),
        DummyNotifier("email"),
        DummyNotifier("webhook"),
    ]
    svc = NotificationService(
        notifiers=notifiers,
        policy=NotifyPolicy(
            warning_to_slack=False,
            warning_to_email=False,
            warning_to_webhook=True,
            cooldown_sec=300,
        ),
        state_path=tmp_path / "state.json",
    )
    out = svc.dispatch([_alert("warning")])
    assert len(out) == 1
    assert str(out[0]["channel"]) == "webhook"


def test_send_failure_is_recorded(tmp_path: Path) -> None:
    notifiers: list[Notifier] = [DummyNotifier("webhook", ok=False)]
    svc = NotificationService(notifiers=notifiers, state_path=tmp_path / "state.json")
    out = svc.dispatch([_alert("critical")])
    assert len(out) == 1
    assert bool(out[0]["success"]) is False
    assert str(out[0]["error_reason"]) == "send_failed"


def test_cooldown_suppresses_duplicate_alert(tmp_path: Path) -> None:
    notifiers: list[Notifier] = [DummyNotifier("webhook")]
    svc = NotificationService(
        notifiers=notifiers,
        policy=NotifyPolicy(cooldown_sec=3600),
        state_path=tmp_path / "state.json",
    )
    out1 = svc.dispatch([_alert("critical")])
    out2 = svc.dispatch([_alert("critical")])
    assert len(out1) == 1
    assert len(out2) == 0


def test_channel_degraded_emitted_after_consecutive_failures(tmp_path: Path) -> None:
    notifiers: list[Notifier] = [DummyNotifier("webhook", ok=False)]
    svc = NotificationService(
        notifiers=notifiers,
        policy=NotifyPolicy(cooldown_sec=0, degraded_threshold=3),
        state_path=tmp_path / "state.json",
    )
    svc.dispatch([_alert("critical")])
    svc.dispatch([_alert("critical")])
    out = svc.dispatch([_alert("critical")])
    codes = {str(r["alert_code"]) for r in out}
    assert "NOTIFY_CHANNEL_DEGRADED" in codes
