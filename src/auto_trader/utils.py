from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        if isinstance(value, bool):
            return float(int(value))
        x = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    try:
        import math

        if math.isnan(x):
            return default
    except Exception:
        pass
    return x


def coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def parse_csv(value: object, *, upper: bool = False) -> tuple[str, ...]:
    if isinstance(value, list | tuple):
        source = value
    elif isinstance(value, str):
        source = [item.strip() for item in value.split(",") if item.strip()]
    else:
        source = []
    seen: set[str] = set()
    ordered: list[str] = []
    for item in source:
        token = str(item).strip()
        if upper:
            token = token.upper()
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)
    return tuple(ordered)


def write_json_file(
    path: str | Path,
    payload: object,
    *,
    indent: int | None = 2,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=True, indent=indent),
        encoding="utf-8",
    )
    return target


def append_jsonl(path: str | Path, row: dict[str, object]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")


def load_json_object(
    payload: str | Path | dict[str, Any] | None,
) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, str | Path):
        loaded = json.loads(Path(payload).read_text(encoding="utf-8"))
        return cast(dict[str, Any], loaded) if isinstance(loaded, dict) else {}
    return payload if isinstance(payload, dict) else {}


def load_json_rows(
    summary: str | Path | dict[str, Any],
    *,
    key: str = "rows",
) -> list[dict[str, Any]]:
    payload = load_json_object(summary)
    rows = payload.get(key, [])
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []
