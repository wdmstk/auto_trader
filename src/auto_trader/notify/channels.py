from __future__ import annotations

import json
import smtplib
from collections.abc import Callable
from email.message import EmailMessage
from urllib.error import URLError
from urllib.request import Request, urlopen

from auto_trader.notify.models import AlertMessage, SendResult

HttpSender = Callable[[Request, float], tuple[int, str]]
EmailSender = Callable[[str, int, EmailMessage], tuple[bool, str]]


class Notifier:
    channel_name: str

    def send(self, alert: AlertMessage) -> SendResult:
        raise NotImplementedError


class SlackNotifier(Notifier):
    channel_name = "slack"

    def __init__(
        self,
        *,
        webhook_url: str,
        sender: HttpSender | None = None,
        timeout_sec: float = 5.0,
    ) -> None:
        self.webhook_url = webhook_url
        self.sender = sender or _default_http_sender
        self.timeout_sec = timeout_sec

    def send(self, alert: AlertMessage) -> SendResult:
        payload = {"text": _render_text(alert)}
        req = Request(
            self.webhook_url,
            data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return _send_http(self.channel_name, alert.alert_code, req, self.sender, self.timeout_sec)


class WebhookNotifier(Notifier):
    channel_name = "webhook"

    def __init__(
        self,
        *,
        endpoint_url: str,
        headers: dict[str, str] | None = None,
        sender: HttpSender | None = None,
        timeout_sec: float = 5.0,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.headers = headers or {}
        self.sender = sender or _default_http_sender
        self.timeout_sec = timeout_sec

    def send(self, alert: AlertMessage) -> SendResult:
        req = Request(
            self.endpoint_url,
            data=json.dumps(alert.__dict__, ensure_ascii=True).encode("utf-8"),
            headers={"Content-Type": "application/json", **self.headers},
            method="POST",
        )
        return _send_http(self.channel_name, alert.alert_code, req, self.sender, self.timeout_sec)


class EmailNotifier(Notifier):
    channel_name = "email"

    def __init__(
        self,
        *,
        smtp_host: str,
        smtp_port: int,
        from_addr: str,
        to_addrs: list[str],
        sender: EmailSender | None = None,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self.sender = sender or _default_email_sender

    def send(self, alert: AlertMessage) -> SendResult:
        msg = EmailMessage()
        msg["Subject"] = f"[{alert.severity.upper()}] {alert.alert_code}"
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)
        msg.set_content(_render_text(alert))
        ok, reason = self.sender(self.smtp_host, self.smtp_port, msg)
        return SendResult(
            channel=self.channel_name,
            alert_code=alert.alert_code,
            sent_at=alert.detected_at,
            success=ok,
            response_code=200 if ok else 500,
            error_reason="" if ok else reason,
        )


def _render_text(alert: AlertMessage) -> str:
    return (
        f"[{alert.severity.upper()}] {alert.alert_code}\n"
        f"detected_at={alert.detected_at}\n"
        f"source={alert.source}\n"
        f"summary={alert.summary}\n"
        f"action_required={alert.action_required}"
    )


def _send_http(
    channel: str,
    alert_code: str,
    req: Request,
    sender: HttpSender,
    timeout_sec: float,
) -> SendResult:
    try:
        code, _ = sender(req, timeout_sec)
        ok = 200 <= code < 300
        return SendResult(
            channel=channel,
            alert_code=alert_code,
            sent_at="",
            success=ok,
            response_code=code,
            error_reason="" if ok else f"http_{code}",
        )
    except URLError:
        return SendResult(
            channel=channel,
            alert_code=alert_code,
            sent_at="",
            success=False,
            response_code=0,
            error_reason="network_error",
        )
    except TimeoutError:
        return SendResult(
            channel=channel,
            alert_code=alert_code,
            sent_at="",
            success=False,
            response_code=0,
            error_reason="timeout",
        )
    except Exception:
        return SendResult(
            channel=channel,
            alert_code=alert_code,
            sent_at="",
            success=False,
            response_code=0,
            error_reason="send_error",
        )


def _default_http_sender(req: Request, timeout_sec: float) -> tuple[int, str]:
    with urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
        body = resp.read().decode("utf-8")
        return int(resp.status), body


def _default_email_sender(host: str, port: int, msg: EmailMessage) -> tuple[bool, str]:
    try:
        with smtplib.SMTP(host=host, port=port, timeout=5) as smtp:
            smtp.send_message(msg)
        return True, ""
    except Exception:
        return False, "smtp_error"
