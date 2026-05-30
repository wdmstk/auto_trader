from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


class AlertStore:
    def __init__(self, root_dir: str | Path = "data/ops") -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def parquet_path(self) -> Path:
        return self.root_dir / "alerts.parquet"

    def jsonl_path(self) -> Path:
        return self.root_dir / "alerts.jsonl"

    def save(self, alerts_df: pd.DataFrame) -> tuple[Path, Path]:
        p_parquet = self.parquet_path()
        p_jsonl = self.jsonl_path()
        alerts_df.to_parquet(p_parquet, index=False)
        with p_jsonl.open("w", encoding="utf-8") as f:
            for row in alerts_df.to_dict(orient="records"):
                f.write(json.dumps(row, ensure_ascii=True) + "\n")
        return p_parquet, p_jsonl
