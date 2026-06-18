from __future__ import annotations

from email.message import EmailMessage
from urllib.error import URLError
from urllib.request import Request

from auto_trader.notify.channels import (
    EmailNotifier,
    SlackNotifier,
    WebhookNotifier,
    _render_text,
    _send_http,
)
from auto_trader.notify.models import AlertMessage


def _alert() -> AlertMessage:
    return AlertMessage(
        alert_code="TEST_ALERT",
        severity="critical",
        detected_at="2026-01-01T00:00:00+00:00",
        source="test",
        summary="test summary",
        action_required="none",
    )


def test_render_text_formats_all_fields() -> None:
    text = _render_text(_alert())
    assert "[CRITICAL] TEST_ALERT" in text
    assert "detected_at=2026-01-01T00:00:00+00:00" in text
    assert "source=test" in text
    assert "summary=test summary" in text
    assert "action_required=none" in text


def test_slack_notifier_sends_via_http_sender() -> None:
    seen: dict[str, object] = {}

    def sender(req: Request, timeout: float) -> tuple[int, str]:
        seen["url"] = req.full_url
        seen["method"] = req.method
        seen["timeout"] = timeout
        return 200, "ok"

    notifier = SlackNotifier(webhook_url="https://hooks.slack.test/x", sender=sender, timeout_sec=3.0)
    result = notifier.send(_alert())
    assert result.success is True
    assert result.channel == "slack"
    assert result.response_code == 200
    assert seen["url"] == "https://hooks.slack.test/x"
    assert seen["method"] == "POST"
    assert seen["timeout"] == 3.0


def test_webhook_notifier_sends_via_http_sender() -> None:
    seen: dict[str, object] = {}

    def sender(req: Request, timeout: float) -> tuple[int, str]:
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        return 200, "ok"

    notifier = WebhookNotifier(
        endpoint_url="https://wh.test/alert",
        headers={"X-Custom": "val"},
        sender=sender,
    )
    result = notifier.send(_alert())
    assert result.success is True
    assert result.channel == "webhook"
    headers = seen.get("headers", {})
    assert isinstance(headers, dict)
    assert headers.get("X-custom") == "val"


def test_email_notifier_sends_via_email_sender() -> None:
    seen: dict[str, object] = {}

    def sender(host: str, port: int, msg: EmailMessage) -> tuple[bool, str]:
        seen["host"] = host
        seen["port"] = port
        seen["subject"] = msg["Subject"]
        seen["from"] = msg["From"]
        seen["to"] = msg["To"]
        return True, ""

    notifier = EmailNotifier(
        smtp_host="smtp.test",
        smtp_port=587,
        from_addr="from@test.com",
        to_addrs=["to1@test.com", "to2@test.com"],
        sender=sender,
    )
    result = notifier.send(_alert())
    assert result.success is True
    assert result.channel == "email"
    assert result.response_code == 200
    assert seen["host"] == "smtp.test"
    assert seen["port"] == 587
    assert "[CRITICAL] TEST_ALERT" in str(seen["subject"])
    assert seen["from"] == "from@test.com"
    assert "to1@test.com" in str(seen["to"])


def test_email_notifier_records_failure() -> None:
    def sender(host: str, port: int, msg: EmailMessage) -> tuple[bool, str]:
        return False, "smtp_timeout"

    notifier = EmailNotifier(
        smtp_host="smtp.test",
        smtp_port=587,
        from_addr="from@test.com",
        to_addrs=["to@test.com"],
        sender=sender,
    )
    result = notifier.send(_alert())
    assert result.success is False
    assert result.response_code == 500
    assert result.error_reason == "smtp_timeout"


def test_send_http_handles_non_success_code() -> None:
    def sender(req: Request, timeout: float) -> tuple[int, str]:
        return 403, "forbidden"

    result = _send_http("test_ch", "CODE", Request("https://test"), sender, 5.0)
    assert result.success is False
    assert result.response_code == 403
    assert result.error_reason == "http_403"


def test_send_http_handles_url_error() -> None:
    def sender(req: Request, timeout: float) -> tuple[int, str]:
        raise URLError("dns failure")

    result = _send_http("test_ch", "CODE", Request("https://test"), sender, 5.0)
    assert result.success is False
    assert result.response_code == 0
    assert result.error_reason == "network_error"


def test_send_http_handles_timeout_error() -> None:
    def sender(req: Request, timeout: float) -> tuple[int, str]:
        raise TimeoutError("timed out")

    result = _send_http("test_ch", "CODE", Request("https://test"), sender, 5.0)
    assert result.success is False
    assert result.response_code == 0
    assert result.error_reason == "timeout"


def test_send_http_handles_generic_exception() -> None:
    def sender(req: Request, timeout: float) -> tuple[int, str]:
        raise RuntimeError("unexpected")

    result = _send_http("test_ch", "CODE", Request("https://test"), sender, 5.0)
    assert result.success is False
    assert result.response_code == 0
    assert result.error_reason == "send_error"


def test_send_http_success_code_200() -> None:
    def sender(req: Request, timeout: float) -> tuple[int, str]:
        return 200, "ok"

    result = _send_http("test_ch", "CODE", Request("https://test"), sender, 5.0)
    assert result.success is True
    assert result.response_code == 200
    assert result.error_reason == ""


def test_send_http_success_code_299() -> None:
    def sender(req: Request, timeout: float) -> tuple[int, str]:
        return 299, "ok"

    result = _send_http("test_ch", "CODE", Request("https://test"), sender, 5.0)
    assert result.success is True
    assert result.response_code == 299
