from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AlertMessage:
    alert_code: str
    severity: str
    detected_at: str
    source: str
    summary: str
    action_required: str


@dataclass(frozen=True)
class SendResult:
    channel: str
    alert_code: str
    sent_at: str
    success: bool
    response_code: int
    error_reason: str


def alert_from_row(row: dict[str, str]) -> AlertMessage:
    return AlertMessage(
        alert_code=str(row.get("alert_code", "")),
        severity=str(row.get("severity", "")),
        detected_at=str(row.get("detected_at", "")),
        source=str(row.get("source", "")),
        summary=str(row.get("summary", "")),
        action_required=str(row.get("action_required", "")),
    )
