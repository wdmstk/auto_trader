from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from auto_trader.gui.state import Action, ControlEvent, append_control_event
from auto_trader.runtime.control import FileStateControlHandler, process_control_events_once
from auto_trader.stateio import StateLockTimeoutError

pytestmark = pytest.mark.smoke


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


def test_runtime_control_recovers_from_backup_when_primary_is_corrupted(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime" / "control_state.json"
    h = FileStateControlHandler(state_path=state_path)
    h.on_start()
    h.on_emergency_stop()
    state_path.write_text("{broken json", encoding="utf-8")

    current = h._read()
    assert current.emergency_stop is False
    assert current.trading_enabled is True


def test_runtime_control_write_fails_when_lock_is_held(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime" / "control_state.json"
    h = FileStateControlHandler(state_path=state_path, lock_timeout_sec=0.01)
    h._lock_path().parent.mkdir(parents=True, exist_ok=True)
    h._lock_path().write_text("locked", encoding="utf-8")
    with pytest.raises(StateLockTimeoutError):
        h.on_start()


def test_runtime_control_recovers_from_stale_lock_with_dead_pid(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime" / "control_state.json"
    h = FileStateControlHandler(state_path=state_path, lock_timeout_sec=0.05)
    lock_path = h._lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps({"pid": 999999, "created_at": 0.0}),
        encoding="utf-8",
    )

    h.on_start()

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["trading_enabled"] is True
    assert not lock_path.exists()
