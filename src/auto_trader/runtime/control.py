from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from auto_trader.gui.control_bridge import ControlDispatchResult, dispatch_control_events


@dataclass(frozen=True)
class RuntimeControlState:
    trading_enabled: bool
    emergency_stop: bool
    close_all_requested: bool
    updated_at: str


class FileStateControlHandler:
    def __init__(self, state_path: str | Path = "data/runtime/control_state.json") -> None:
        self.state_path = Path(state_path)

    def on_start(self) -> None:
        self._write(
            RuntimeControlState(
                trading_enabled=True,
                emergency_stop=False,
                close_all_requested=False,
                updated_at=_now_iso(),
            )
        )

    def on_stop(self) -> None:
        state = self._read()
        self._write(
            RuntimeControlState(
                trading_enabled=False,
                emergency_stop=state.emergency_stop,
                close_all_requested=state.close_all_requested,
                updated_at=_now_iso(),
            )
        )

    def on_emergency_stop(self) -> None:
        self._write(
            RuntimeControlState(
                trading_enabled=False,
                emergency_stop=True,
                close_all_requested=True,
                updated_at=_now_iso(),
            )
        )

    def on_emergency_cancel(self) -> None:
        state = self._read()
        self._write(
            RuntimeControlState(
                trading_enabled=state.trading_enabled,
                emergency_stop=False,
                close_all_requested=state.close_all_requested,
                updated_at=_now_iso(),
            )
        )

    def on_close_all(self) -> None:
        state = self._read()
        self._write(
            RuntimeControlState(
                trading_enabled=False,
                emergency_stop=state.emergency_stop,
                close_all_requested=True,
                updated_at=_now_iso(),
            )
        )

    def _read(self) -> RuntimeControlState:
        if not self.state_path.exists():
            return RuntimeControlState(
                trading_enabled=False,
                emergency_stop=False,
                close_all_requested=False,
                updated_at=_now_iso(),
            )
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return RuntimeControlState(
                trading_enabled=bool(payload.get("trading_enabled", False)),
                emergency_stop=bool(payload.get("emergency_stop", False)),
                close_all_requested=bool(payload.get("close_all_requested", False)),
                updated_at=str(payload.get("updated_at", _now_iso())),
            )
        except Exception:
            return RuntimeControlState(
                trading_enabled=False,
                emergency_stop=False,
                close_all_requested=False,
                updated_at=_now_iso(),
            )

    def _write(self, state: RuntimeControlState) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(
                {
                    "trading_enabled": state.trading_enabled,
                    "emergency_stop": state.emergency_stop,
                    "close_all_requested": state.close_all_requested,
                    "updated_at": state.updated_at,
                },
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )


def process_control_events_once(
    *,
    control_log_path: str | Path = "data/gui/control_events.jsonl",
    cursor_path: str | Path = "data/runtime/control_cursor.json",
    state_path: str | Path = "data/runtime/control_state.json",
) -> ControlDispatchResult:
    handler = FileStateControlHandler(state_path=state_path)
    return dispatch_control_events(
        control_log_path=control_log_path,
        handler=handler,
        cursor_path=cursor_path,
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
