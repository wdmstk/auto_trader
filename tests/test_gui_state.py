from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.gui.state import ControlEvent, append_control_event, emergency_badge, is_stale


def test_is_stale() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    old = now - timedelta(seconds=40)
    fresh = now - timedelta(seconds=10)
    assert is_stale(old, now, max_delay_sec=30) is True
    assert is_stale(fresh, now, max_delay_sec=30) is False


def test_emergency_badge_priority() -> None:
    assert emergency_badge(True, "RANGE") == "EMERGENCY"
    assert emergency_badge(False, "HIGH_VOL") == "HIGH_VOL"
    assert emergency_badge(False, "RANGE") == "NORMAL"


def test_append_control_event_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    now = datetime(2026, 1, 1, tzinfo=UTC)
    append_control_event(
        path,
        ControlEvent(
            action="EMERGENCY_STOP",
            requested_at=now,
            applied_at=now,
            result="accepted",
        ),
    )
    df = pd.read_json(path, lines=True)
    assert len(df) == 1
    assert df.iloc[0]["action"] == "EMERGENCY_STOP"
