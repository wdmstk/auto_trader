from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class StateLockTimeoutError(RuntimeError):
    pass


class FileLock:
    def __init__(
        self,
        path: str | Path,
        timeout_sec: float = 1.0,
        poll_sec: float = 0.02,
        stale_timeout_sec: float = 300.0,
    ) -> None:
        self.path = Path(path)
        self.timeout_sec = timeout_sec
        self.poll_sec = poll_sec
        self.stale_timeout_sec = stale_timeout_sec
        self._locked = False

    def __enter__(self) -> FileLock:
        start = time.monotonic()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(
                        {"pid": os.getpid(), "created_at": time.time()},
                        f,
                        ensure_ascii=True,
                    )
                    f.flush()
                    os.fsync(f.fileno())
                self._locked = True
                return self
            except FileExistsError:
                if self._reclaim_if_stale():
                    continue
                if (time.monotonic() - start) >= self.timeout_sec:
                    raise StateLockTimeoutError(f"timed out acquiring lock: {self.path}") from None
                time.sleep(self.poll_sec)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._locked:
            self.path.unlink(missing_ok=True)
            self._locked = False

    def _reclaim_if_stale(self) -> bool:
        lock_info = _read_lock_info(self.path)
        if lock_info is None:
            return False
        pid, created_at = lock_info
        if not _is_stale_lock(
            pid=pid,
            created_at=created_at,
            stale_timeout_sec=self.stale_timeout_sec,
            path=self.path,
        ):
            return False
        self.path.unlink(missing_ok=True)
        return True


def atomic_write_file(
    path: str | Path,
    *,
    writer: Callable[[Path], None],
    make_backup: bool = True,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    backup = target.with_suffix(f"{target.suffix}.bak")
    writer(tmp)
    if make_backup and target.exists():
        shutil.copy2(target, backup)
    os.replace(tmp, target)
    return target


def atomic_write_json(path: str | Path, payload: dict[str, object], *, make_backup: bool = True) -> Path:
    def _write(tmp_path: Path) -> None:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=True)
            f.flush()
            os.fsync(f.fileno())

    return atomic_write_file(path, writer=_write, make_backup=make_backup)


def read_json_with_recovery(path: str | Path) -> dict[str, object]:
    target = Path(path)
    backup = target.with_suffix(f"{target.suffix}.bak")
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        logger.warning("state file unreadable at %s, trying backup", target, exc_info=True)
    try:
        payload = json.loads(backup.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            logger.info("recovered state from backup %s", backup)
            return payload
    except Exception:
        if target.exists() or backup.exists():
            logger.warning("state recovery failed for %s (backup also unreadable)", target, exc_info=True)
    return {}


def _read_lock_info(path: Path) -> tuple[int | None, float | None] | None:
    def _maybe_int(value: object) -> int | None:
        try:
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str):
                return int(value)
            return None
        except Exception:
            return None

    def _maybe_float(value: object) -> float | None:
        try:
            if isinstance(value, bool):
                return float(value)
            if isinstance(value, int | float):
                return float(value)
            if isinstance(value, str):
                return float(value)
            return None
        except Exception:
            return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = None
    if isinstance(payload, dict):
        pid = payload.get("pid")
        created_at = payload.get("created_at")
        return _maybe_int(pid), _maybe_float(created_at)
    if isinstance(payload, int):
        return payload, None
    if isinstance(payload, str) and payload.isdigit():
        return int(payload), None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except Exception:
        pid = None
    try:
        created_at = path.stat().st_mtime
    except FileNotFoundError:
        return None
    return pid, created_at


def _is_stale_lock(
    *,
    pid: int | None,
    created_at: float | None,
    stale_timeout_sec: float,
    path: Path,
) -> bool:
    if pid is not None and not _pid_is_alive(pid):
        return True
    if stale_timeout_sec <= 0:
        return False
    try:
        age_sec = time.time() - (created_at if created_at is not None else path.stat().st_mtime)
    except FileNotFoundError:
        return False
    return age_sec >= stale_timeout_sec


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
