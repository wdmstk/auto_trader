from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from auto_trader.gui.control_bridge import dispatch_control_events
from auto_trader.gui.state import Action, ControlEvent, append_control_event


@dataclass
class DummyHandler:
    calls: list[str] = field(default_factory=list)

    def on_start(self) -> None:
        self.calls.append("START")

    def on_stop(self) -> None:
        self.calls.append("STOP")

    def on_emergency_stop(self) -> None:
        self.calls.append("EMERGENCY_STOP")

    def on_emergency_cancel(self) -> None:
        self.calls.append("EMERGENCY_CANCEL")

    def on_close_all(self) -> None:
        self.calls.append("CLOSE_ALL")


def _append(log_path: Path, action: str, ts: datetime) -> None:
    append_control_event(
        log_path,
        ControlEvent(
            action=cast(Action, action),
            requested_at=ts,
            applied_at=ts,
            result="accepted",
        ),
    )


def test_dispatch_control_events_end_to_end_with_cursor(tmp_path: Path) -> None:
    log_path = tmp_path / "control_events.jsonl"
    cursor_path = tmp_path / "control_cursor.json"
    base = datetime(2026, 1, 1, tzinfo=UTC)

    _append(log_path, "START", base)
    _append(log_path, "EMERGENCY_STOP", base)

    handler = DummyHandler()
    first = dispatch_control_events(
        control_log_path=log_path,
        handler=handler,
        cursor_path=cursor_path,
    )
    assert first.processed == 2
    assert first.actions == ["START", "EMERGENCY_STOP"]
    assert handler.calls == ["START", "EMERGENCY_STOP"]

    second = dispatch_control_events(
        control_log_path=log_path,
        handler=handler,
        cursor_path=cursor_path,
    )
    assert second.processed == 0
    assert second.actions == []
    assert handler.calls == ["START", "EMERGENCY_STOP"]

    _append(log_path, "CLOSE_ALL", base)
    third = dispatch_control_events(
        control_log_path=log_path,
        handler=handler,
        cursor_path=cursor_path,
    )
    assert third.processed == 1
    assert third.actions == ["CLOSE_ALL"]
    assert handler.calls == ["START", "EMERGENCY_STOP", "CLOSE_ALL"]


def test_dispatch_control_events_quarantines_invalid_lines(tmp_path: Path) -> None:
    log_path = tmp_path / "control_events.jsonl"
    quarantine_path = tmp_path / "control_events.bad.jsonl"
    cursor_path = tmp_path / "control_cursor.json"
    log_path.write_text(
        "\n".join(
            [
                json.dumps({"action": "START"}),
                "{broken json",
                json.dumps({"action": "NOPE"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    handler = DummyHandler()
    result = dispatch_control_events(
        control_log_path=log_path,
        handler=handler,
        cursor_path=cursor_path,
        quarantine_path=quarantine_path,
    )

    assert result.processed == 1
    assert result.actions == ["START"]
    assert handler.calls == ["START"]
    quarantined = quarantine_path.read_text(encoding="utf-8").splitlines()
    assert len(quarantined) == 2
