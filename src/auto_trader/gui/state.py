from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

Action = Literal["START", "STOP", "EMERGENCY_STOP", "EMERGENCY_CANCEL", "CLOSE_ALL"]


@dataclass(frozen=True)
class ControlEvent:
    action: Action
    requested_at: datetime
    applied_at: datetime
    result: str


def is_stale(updated_at: datetime, now: datetime | None = None, max_delay_sec: int = 30) -> bool:
    ref = now or datetime.now(UTC)
    return (ref - updated_at) > timedelta(seconds=max_delay_sec)


def emergency_badge(emergency_state: bool, regime: str) -> str:
    if emergency_state:
        return "EMERGENCY"
    if regime == "HIGH_VOL":
        return "HIGH_VOL"
    return "NORMAL"


def append_control_event(path: str | Path, event: ControlEvent) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "action": event.action,
        "requested_at": event.requested_at.isoformat(),
        "applied_at": event.applied_at.isoformat(),
        "result": event.result,
    }
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")
    return out
