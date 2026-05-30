from __future__ import annotations

from pathlib import Path

import pandas as pd


class LabelParquetStore:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, symbol: str, timeframe: str) -> Path:
        return self.root_dir / f"{symbol}_{timeframe}_labels.parquet"

    def save(self, symbol: str, timeframe: str, labels_df: pd.DataFrame) -> Path:
        path = self.path_for(symbol, timeframe)
        labels_df.to_parquet(path, index=False)
        return path

    def read(self, symbol: str, timeframe: str) -> pd.DataFrame:
        path = self.path_for(symbol, timeframe)
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)
