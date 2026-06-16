from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from auto_trader.exchange.ws_client import ExecutionStreamEvent
from auto_trader.stateio import FileLock, read_json_with_recovery

ParsedExecutionEvent = ExecutionStreamEvent


def reconcile_execution_events_once(
    *,
    events_path: str | Path,
    cursor_path: str | Path,
    parse_message: Callable[[str], ParsedExecutionEvent | None],
    handle_event: Callable[[ParsedExecutionEvent], bool],
) -> dict[str, object]:
    events_path = Path(events_path)
    cursor_path = Path(cursor_path)
    if not events_path.exists():
        return {"processed": 0, "applied": 0, "invalid": 0, "ignored": 0}

    lines = events_path.read_text(encoding="utf-8").splitlines()
    start_index = _read_line_cursor(cursor_path)
    if start_index >= len(lines):
        return {"processed": 0, "applied": 0, "invalid": 0, "ignored": 0}

    processed = 0
    applied = 0
    invalid = 0
    ignored = 0
    for line in lines[start_index:]:
        processed += 1
        event = parse_message(line)
        if event is None:
            invalid += 1
            continue
        if event.status not in {
            "partial_filled",
            "partially_filled",
            "filled",
            "canceled",
            "expired",
        }:
            ignored += 1
            continue
        if handle_event(event):
            applied += 1
        else:
            ignored += 1

    _write_line_cursor(cursor_path, len(lines))
    return {
        "processed": processed,
        "applied": applied,
        "invalid": invalid,
        "ignored": ignored,
    }


def _read_line_cursor(path: Path) -> int:
    payload = read_json_with_recovery(path)
    value = payload.get("last_processed_line", 0) if isinstance(payload, dict) else 0
    try:
        if isinstance(value, bool):
            return max(int(value), 0)
        if isinstance(value, int):
            return max(value, 0)
        if isinstance(value, float):
            return max(int(value), 0)
        if isinstance(value, str):
            return max(int(value), 0)
        return 0
    except (TypeError, ValueError):
        return 0


def _write_line_cursor(path: Path, line_no: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_processed_line": max(int(line_no), 0),
    }
    with FileLock(path.with_suffix(f"{path.suffix}.lock"), timeout_sec=1.0):
        path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
