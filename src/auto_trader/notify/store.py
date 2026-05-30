from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


class NotificationStore:
    def __init__(self, root_dir: str | Path = "data/ops") -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def jsonl_path(self) -> Path:
        return self.root_dir / "notifications.jsonl"

    def append(self, rows: list[dict[str, object]]) -> Path:
        path = self.jsonl_path()
        with path.open("a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")
        return path

    def read(self) -> pd.DataFrame:
        path = self.jsonl_path()
        if not path.exists():
            return pd.DataFrame()
        return pd.read_json(path, lines=True)
