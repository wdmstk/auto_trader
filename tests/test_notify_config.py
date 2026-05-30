from __future__ import annotations

import pytest

from auto_trader.notify.config import build_notifiers_from_env


def test_build_notifiers_from_env_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTO_TRADER_NOTIFY_SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("AUTO_TRADER_NOTIFY_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("AUTO_TRADER_NOTIFY_SMTP_HOST", raising=False)
    monkeypatch.delenv("AUTO_TRADER_NOTIFY_EMAIL_FROM", raising=False)
    monkeypatch.delenv("AUTO_TRADER_NOTIFY_EMAIL_TO", raising=False)
    out = build_notifiers_from_env()
    assert out == []


def test_build_notifiers_from_env_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_TRADER_NOTIFY_SLACK_WEBHOOK_URL", "https://slack.test")
    monkeypatch.setenv("AUTO_TRADER_NOTIFY_WEBHOOK_URL", "https://webhook.test")
    monkeypatch.setenv("AUTO_TRADER_NOTIFY_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("AUTO_TRADER_NOTIFY_EMAIL_FROM", "bot@test")
    monkeypatch.setenv("AUTO_TRADER_NOTIFY_EMAIL_TO", "a@test,b@test")
    out = build_notifiers_from_env()
    assert len(out) == 3
