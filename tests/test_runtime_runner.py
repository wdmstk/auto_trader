from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from auto_trader.gui.state import ControlEvent, append_control_event
from auto_trader.runtime.runner import run_control_event_watch


def test_run_control_event_watch_applies_events(tmp_path: Path) -> None:
    control_log = tmp_path / "gui" / "control_events.jsonl"
    cursor_path = tmp_path / "runtime" / "control_cursor.json"
    state_path = tmp_path / "runtime" / "control_state.json"
    now = datetime(2026, 1, 1, tzinfo=UTC)
    append_control_event(
        control_log,
        ControlEvent(action="START", requested_at=now, applied_at=now, result="accepted"),
    )

    count = run_control_event_watch(
        control_log_path=control_log,
        cursor_path=cursor_path,
        state_path=state_path,
        interval_sec=0.1,
        max_iterations=1,
    )
    assert count == 1
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["trading_enabled"] is True
