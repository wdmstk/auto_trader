from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from auto_trader.notify.channels import Notifier
from auto_trader.notify.models import AlertMessage, SendResult
from auto_trader.notify.service import NotificationService, NotifyPolicy
from auto_trader.stateio import StateLockTimeoutError


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


def test_notify_state_recovers_from_backup_when_primary_is_corrupted(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    svc = NotificationService(
        notifiers=[DummyNotifier("webhook")],
        policy=NotifyPolicy(cooldown_sec=3600),
        state_path=state_path,
    )
    svc.dispatch([_alert("critical")])
    svc.dispatch([_alert("warning")])  # creates backup
    state_path.write_text("{broken", encoding="utf-8")

    out = svc.dispatch([_alert("critical")])
    assert len(out) == 0


def test_notify_write_fails_when_lock_is_held(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    svc = NotificationService(
        notifiers=[DummyNotifier("webhook")],
        state_path=state_path,
        lock_timeout_sec=0.01,
    )
    lock_path = state_path.with_suffix(".json.lock")
    lock_path.write_text("locked", encoding="utf-8")
    with pytest.raises(StateLockTimeoutError):
        svc.dispatch([_alert("critical")])
