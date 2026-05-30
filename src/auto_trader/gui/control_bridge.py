from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

from auto_trader.gui.state import Action


class ControlActionHandler(Protocol):
    def on_start(self) -> None: ...
    def on_stop(self) -> None: ...
    def on_emergency_stop(self) -> None: ...
    def on_emergency_cancel(self) -> None: ...
    def on_close_all(self) -> None: ...


@dataclass(frozen=True)
class ControlDispatchResult:
    processed: int
    actions: list[Action]


def dispatch_control_events(
    *,
    control_log_path: str | Path,
    handler: ControlActionHandler,
    cursor_path: str | Path | None = None,
) -> ControlDispatchResult:
    log_path = Path(control_log_path)
    if not log_path.exists():
        return ControlDispatchResult(processed=0, actions=[])

    lines = log_path.read_text(encoding="utf-8").splitlines()
    cursor = Path(cursor_path) if cursor_path is not None else None
    start_index = _read_cursor(cursor) if cursor is not None else 0
    if start_index >= len(lines):
        return ControlDispatchResult(processed=0, actions=[])

    seen_actions: list[Action] = []
    for line in lines[start_index:]:
        raw = json.loads(line)
        action = str(raw.get("action", "")).upper()
        if action not in {"START", "STOP", "EMERGENCY_STOP", "EMERGENCY_CANCEL", "CLOSE_ALL"}:
            continue
        typed_action = cast(Action, action)
        _dispatch(typed_action, handler)
        seen_actions.append(typed_action)

    if cursor is not None:
        _write_cursor(cursor, len(lines))
    return ControlDispatchResult(processed=len(seen_actions), actions=seen_actions)


def _dispatch(action: Action, handler: ControlActionHandler) -> None:
    if action == "START":
        handler.on_start()
    elif action == "STOP":
        handler.on_stop()
    elif action == "EMERGENCY_STOP":
        handler.on_emergency_stop()
    elif action == "EMERGENCY_CANCEL":
        handler.on_emergency_cancel()
    elif action == "CLOSE_ALL":
        handler.on_close_all()


def _read_cursor(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = int(payload.get("last_processed_line", 0))
    except Exception:
        return 0
    return max(value, 0)


def _write_cursor(path: Path, line_no: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_processed_line": max(line_no, 0),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
