from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from auto_trader.exchange.ws_client import ExecutionStreamEvent
from auto_trader.worker.execution_sync import reconcile_execution_events_once


def _make_event(
    *,
    order_id: str = "100",
    symbol: str = "BTCUSDT",
    status: str = "filled",
    side: str = "buy",
) -> ExecutionStreamEvent:
    return ExecutionStreamEvent(
        order_id=order_id,
        client_order_id="cid_001",
        symbol=symbol,
        side=side,
        status=status,
        filled_qty=0.1,
        avg_fill_price=65000.0,
        event_ts=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _parser(line: str) -> ExecutionStreamEvent | None:
    try:
        data = json.loads(line)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return _make_event(
        order_id=str(data.get("order_id", "")),
        status=str(data.get("status", "")),
    )


def test_returns_zero_when_events_file_missing(tmp_path: Path) -> None:
    result = reconcile_execution_events_once(
        events_path=tmp_path / "events.jsonl",
        cursor_path=tmp_path / "cursor.json",
        parse_message=_parser,
        handle_event=lambda e: True,
    )
    assert result == {"processed": 0, "applied": 0, "invalid": 0, "ignored": 0}


def test_processes_filled_events(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    cursor = tmp_path / "cursor.json"
    events.write_text(
        json.dumps({"order_id": "1", "status": "filled"}) + "\n"
        + json.dumps({"order_id": "2", "status": "filled"}) + "\n",
        encoding="utf-8",
    )
    result = reconcile_execution_events_once(
        events_path=events,
        cursor_path=cursor,
        parse_message=_parser,
        handle_event=lambda e: True,
    )
    assert result["processed"] == 2
    assert result["applied"] == 2
    assert result["invalid"] == 0
    assert result["ignored"] == 0


def test_tracks_cursor_across_calls(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    cursor = tmp_path / "cursor.json"
    events.write_text(
        json.dumps({"order_id": "1", "status": "filled"}) + "\n",
        encoding="utf-8",
    )
    reconcile_execution_events_once(
        events_path=events,
        cursor_path=cursor,
        parse_message=_parser,
        handle_event=lambda e: True,
    )

    # Second call with same events should process nothing
    result = reconcile_execution_events_once(
        events_path=events,
        cursor_path=cursor,
        parse_message=_parser,
        handle_event=lambda e: True,
    )
    assert result["processed"] == 0


def test_counts_invalid_lines(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    cursor = tmp_path / "cursor.json"
    events.write_text(
        "not json\n" + json.dumps({"order_id": "1", "status": "filled"}) + "\n",
        encoding="utf-8",
    )
    result = reconcile_execution_events_once(
        events_path=events,
        cursor_path=cursor,
        parse_message=_parser,
        handle_event=lambda e: True,
    )
    assert result["processed"] == 2
    assert result["invalid"] == 1
    assert result["applied"] == 1


def test_ignores_non_actionable_statuses(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    cursor = tmp_path / "cursor.json"
    events.write_text(
        json.dumps({"order_id": "1", "status": "new"}) + "\n",
        encoding="utf-8",
    )
    result = reconcile_execution_events_once(
        events_path=events,
        cursor_path=cursor,
        parse_message=_parser,
        handle_event=lambda e: True,
    )
    assert result["processed"] == 1
    assert result["ignored"] == 1
    assert result["applied"] == 0


def test_counts_ignored_when_handler_returns_false(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    cursor = tmp_path / "cursor.json"
    events.write_text(
        json.dumps({"order_id": "1", "status": "filled"}) + "\n",
        encoding="utf-8",
    )
    result = reconcile_execution_events_once(
        events_path=events,
        cursor_path=cursor,
        parse_message=_parser,
        handle_event=lambda e: False,
    )
    assert result["processed"] == 1
    assert result["applied"] == 0
    assert result["ignored"] == 1


def test_handles_partially_filled_status(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    cursor = tmp_path / "cursor.json"
    events.write_text(
        json.dumps({"order_id": "1", "status": "partially_filled"}) + "\n"
        + json.dumps({"order_id": "2", "status": "partial_filled"}) + "\n",
        encoding="utf-8",
    )
    result = reconcile_execution_events_once(
        events_path=events,
        cursor_path=cursor,
        parse_message=_parser,
        handle_event=lambda e: True,
    )
    assert result["applied"] == 2


def test_handles_canceled_and_expired_status(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    cursor = tmp_path / "cursor.json"
    events.write_text(
        json.dumps({"order_id": "1", "status": "canceled"}) + "\n"
        + json.dumps({"order_id": "2", "status": "expired"}) + "\n",
        encoding="utf-8",
    )
    result = reconcile_execution_events_once(
        events_path=events,
        cursor_path=cursor,
        parse_message=_parser,
        handle_event=lambda e: True,
    )
    assert result["applied"] == 2
