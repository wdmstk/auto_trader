from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from auto_trader.gui.state import Action, ControlEvent, append_control_event
from auto_trader.runtime.control import process_control_events_once


def _append(log_path: Path, action: Action, ts: datetime) -> None:
    append_control_event(
        log_path,
        ControlEvent(action=action, requested_at=ts, applied_at=ts, result="accepted"),
    )


def test_process_control_events_once_updates_runtime_state(tmp_path: Path) -> None:
    log_path = tmp_path / "gui" / "control_events.jsonl"
    cursor_path = tmp_path / "runtime" / "control_cursor.json"
    state_path = tmp_path / "runtime" / "control_state.json"
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    _append(log_path, "START", ts)
    _append(log_path, "EMERGENCY_STOP", ts)
    _append(log_path, "EMERGENCY_CANCEL", ts)
    _append(log_path, "CLOSE_ALL", ts)

    result = process_control_events_once(
        control_log_path=log_path,
        cursor_path=cursor_path,
        state_path=state_path,
    )
    assert result.processed == 4
    assert result.actions == ["START", "EMERGENCY_STOP", "EMERGENCY_CANCEL", "CLOSE_ALL"]

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["trading_enabled"] is False
    assert state["emergency_stop"] is False
    assert state["close_all_requested"] is True

    second = process_control_events_once(
        control_log_path=log_path,
        cursor_path=cursor_path,
        state_path=state_path,
    )
    assert second.processed == 0
    assert second.actions == []
