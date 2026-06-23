from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

from auto_trader.gui.state import Action
from auto_trader.stateio import FileLock
from auto_trader.utils import write_json_file


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
    quarantine_path: str | Path | None = None,
) -> ControlDispatchResult:
    log_path = Path(control_log_path)
    if not log_path.exists():
        return ControlDispatchResult(processed=0, actions=[])
    quarantine = Path(quarantine_path) if quarantine_path is not None else log_path.with_name(f"{log_path.stem}.bad{log_path.suffix}")

    lines = log_path.read_text(encoding="utf-8").splitlines()
    cursor = Path(cursor_path) if cursor_path is not None else None
    start_index = _read_cursor(cursor) if cursor is not None else 0
    if start_index >= len(lines):
        return ControlDispatchResult(processed=0, actions=[])

    seen_actions: list[Action] = []
    for line in lines[start_index:]:
        try:
            raw = json.loads(line)
        except Exception as exc:
            _append_quarantine(quarantine, line, reason=f"invalid_json:{exc.__class__.__name__}")
            continue
        if not isinstance(raw, dict):
            _append_quarantine(quarantine, line, reason="invalid_json:non_object")
            continue
        action = str(raw.get("action", "")).upper()
        if action not in {"START", "STOP", "EMERGENCY_STOP", "EMERGENCY_CANCEL", "CLOSE_ALL"}:
            _append_quarantine(quarantine, line, reason=f"invalid_action:{action or 'missing'}")
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
    payload = {
        "last_processed_line": max(line_no, 0),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    write_json_file(path, payload, indent=None)


def _append_quarantine(path: Path, line: str, *, reason: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    payload = {
        "reason": reason,
        "raw_line": line,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    with FileLock(lock_path, timeout_sec=1.0):
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
