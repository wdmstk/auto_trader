from __future__ import annotations

import time
from pathlib import Path

from auto_trader.runtime.control import process_control_events_once


def run_control_event_watch(
    *,
    control_log_path: str | Path = "data/gui/control_events.jsonl",
    cursor_path: str | Path = "data/runtime/control_cursor.json",
    state_path: str | Path = "data/runtime/control_state.json",
    interval_sec: float = 2.0,
    max_iterations: int | None = None,
) -> int:
    iterations = 0
    while True:
        process_control_events_once(
            control_log_path=control_log_path,
            cursor_path=cursor_path,
            state_path=state_path,
        )
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            return iterations
        time.sleep(max(interval_sec, 0.1))
