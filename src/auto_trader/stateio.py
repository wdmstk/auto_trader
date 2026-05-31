from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")


class StateLockTimeoutError(RuntimeError):
    pass


class FileLock:
    def __init__(self, path: str | Path, timeout_sec: float = 1.0, poll_sec: float = 0.02) -> None:
        self.path = Path(path)
        self.timeout_sec = timeout_sec
        self.poll_sec = poll_sec
        self._locked = False

    def __enter__(self) -> FileLock:
        start = time.monotonic()
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(str(os.getpid()))
                    f.flush()
                    os.fsync(f.fileno())
                self._locked = True
                return self
            except FileExistsError:
                if (time.monotonic() - start) >= self.timeout_sec:
                    raise StateLockTimeoutError(f"timed out acquiring lock: {self.path}") from None
                time.sleep(self.poll_sec)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._locked:
            self.path.unlink(missing_ok=True)
            self._locked = False


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


def atomic_write_json(
    path: str | Path, payload: dict[str, object], *, make_backup: bool = True
) -> Path:
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
        pass
    try:
        payload = json.loads(backup.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}
