from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from auto_trader.stateio import FileLock, atomic_write_json, read_json_with_recovery


@dataclass
class WorkerState:
    last_processed_bars: dict[str, str] = field(default_factory=dict)
    last_results: dict[str, dict[str, object]] = field(default_factory=dict)
    updated_at: str = ""
    last_cycle_at: str = ""
    last_error: str = ""

    @classmethod
    def load(cls, path: str | Path) -> WorkerState:
        p = Path(path)
        lock_path = p.with_suffix(f"{p.suffix}.lock")
        with FileLock(lock_path, timeout_sec=1.0):
            payload = read_json_with_recovery(p)
        if not payload:
            return cls()
        processed = payload.get("last_processed_bars", {})
        results = payload.get("last_results", {})
        return cls(
            last_processed_bars=_as_string_map(processed),
            last_results=_as_result_map(results),
            updated_at=str(payload.get("updated_at", "")),
            last_cycle_at=str(payload.get("last_cycle_at", "")),
            last_error=str(payload.get("last_error", "")),
        )

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        lock_path = p.with_suffix(f"{p.suffix}.lock")
        payload = {
            "last_processed_bars": dict(sorted(self.last_processed_bars.items())),
            "last_results": self.last_results,
            "updated_at": self.updated_at,
            "last_cycle_at": self.last_cycle_at,
            "last_error": self.last_error,
        }
        with FileLock(lock_path, timeout_sec=1.0):
            atomic_write_json(p, payload)
        return p


def _as_string_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, item in value.items():
        text = str(item)
        if text:
            out[str(key)] = text
    return out


def _as_result_map(value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, dict[str, object]] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            out[str(key)] = dict(item)
    return out
