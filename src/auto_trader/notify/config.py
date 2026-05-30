from __future__ import annotations

import os

from auto_trader.notify.channels import EmailNotifier, Notifier, SlackNotifier, WebhookNotifier


def build_notifiers_from_env() -> list[Notifier]:
    out: list[Notifier] = []
    slack_url = os.getenv("AUTO_TRADER_NOTIFY_SLACK_WEBHOOK_URL", "")
    webhook_url = os.getenv("AUTO_TRADER_NOTIFY_WEBHOOK_URL", "")
    smtp_host = os.getenv("AUTO_TRADER_NOTIFY_SMTP_HOST", "")
    smtp_port = os.getenv("AUTO_TRADER_NOTIFY_SMTP_PORT", "587")
    from_addr = os.getenv("AUTO_TRADER_NOTIFY_EMAIL_FROM", "")
    to_addrs_raw = os.getenv("AUTO_TRADER_NOTIFY_EMAIL_TO", "")

    if slack_url:
        out.append(SlackNotifier(webhook_url=slack_url))
    if webhook_url:
        out.append(WebhookNotifier(endpoint_url=webhook_url))
    if smtp_host and from_addr and to_addrs_raw:
        to_addrs = [s.strip() for s in to_addrs_raw.split(",") if s.strip()]
        if to_addrs:
            try:
                port = int(smtp_port)
            except ValueError:
                port = 587
            out.append(
                EmailNotifier(
                    smtp_host=smtp_host,
                    smtp_port=port,
                    from_addr=from_addr,
                    to_addrs=to_addrs,
                )
            )
    return out
