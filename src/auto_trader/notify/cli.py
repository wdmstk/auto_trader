from __future__ import annotations

import argparse
import json
from pathlib import Path

from auto_trader.notify.channels import EmailNotifier, Notifier, SlackNotifier, WebhookNotifier
from auto_trader.notify.pipeline import run_notification_pipeline
from auto_trader.notify.service import NotifyPolicy


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Send alerts to notification channels.")
    p.add_argument("--alerts-path", default="data/ops/alerts.parquet")
    p.add_argument("--output-dir", default="data/ops")
    p.add_argument("--state-path", default="data/ops/notify_state.json")
    p.add_argument("--cooldown-sec", type=int, default=300)
    p.add_argument("--warning-to-slack", action="store_true")
    p.add_argument("--warning-to-email", action="store_true")
    p.add_argument("--warning-to-webhook", action="store_true")

    p.add_argument("--slack-webhook-url", default=None)
    p.add_argument("--webhook-url", default=None)
    p.add_argument("--email-smtp-host", default=None)
    p.add_argument("--email-smtp-port", type=int, default=587)
    p.add_argument("--email-from", default=None)
    p.add_argument("--email-to", default=None, help="comma-separated list")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    notifiers = _build_notifiers(args)
    if not notifiers:
        print(json.dumps({"error": "no notifier configured"}, ensure_ascii=True))
        return 1

    policy = NotifyPolicy(
        warning_to_slack=bool(args.warning_to_slack),
        warning_to_email=bool(args.warning_to_email),
        warning_to_webhook=bool(args.warning_to_webhook),
        cooldown_sec=int(args.cooldown_sec),
    )
    out_df, saved = run_notification_pipeline(
        alerts_path=Path(args.alerts_path),
        notifiers=notifiers,
        output_dir=Path(args.output_dir),
        policy=policy,
        state_path=Path(args.state_path),
    )
    print(json.dumps({"count": len(out_df), "saved": str(saved)}, ensure_ascii=True))
    return 0


def _build_notifiers(args: argparse.Namespace) -> list[Notifier]:
    out: list[Notifier] = []
    if args.slack_webhook_url:
        out.append(SlackNotifier(webhook_url=str(args.slack_webhook_url)))
    if args.webhook_url:
        out.append(WebhookNotifier(endpoint_url=str(args.webhook_url)))
    if args.email_smtp_host and args.email_from and args.email_to:
        to_addrs = [s.strip() for s in str(args.email_to).split(",") if s.strip()]
        if to_addrs:
            out.append(
                EmailNotifier(
                    smtp_host=str(args.email_smtp_host),
                    smtp_port=int(args.email_smtp_port),
                    from_addr=str(args.email_from),
                    to_addrs=to_addrs,
                )
            )
    return out


if __name__ == "__main__":
    raise SystemExit(main())
