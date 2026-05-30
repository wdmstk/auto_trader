from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.ml.pipeline import run_ml_pipeline


def test_run_ml_pipeline_outputs_filter_columns(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    n = 60
    f_rows: list[dict[str, object]] = []
    r_rows: list[dict[str, object]] = []
    s_rows: list[dict[str, object]] = []
    l_rows: list[dict[str, object]] = []

    for i in range(n):
        ts = base + timedelta(minutes=i)
        f_rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "rsi": 35 + (i % 20),
                "atr": 1.0 + i * 0.01,
                "bb_width": 0.04 + (i % 3) * 0.01,
                "momentum_persistence": 0.6,
                "breakout_persistence": 0.6,
                "trend_efficiency": 0.2 + ((i % 5) * 0.01),
            }
        )
        r_rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "regime": "TREND",
                "is_trade_allowed": True,
            }
        )
        s_rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "entry_signal": True,
            }
        )
        l_rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "label": 1 if i % 2 == 0 else 0,
            }
        )

    fpath = tmp_path / "features.parquet"
    rpath = tmp_path / "regime.parquet"
    spath = tmp_path / "signals.parquet"
    lpath = tmp_path / "labels.parquet"
    pd.DataFrame(f_rows).to_parquet(fpath, index=False)
    pd.DataFrame(r_rows).to_parquet(rpath, index=False)
    pd.DataFrame(s_rows).to_parquet(spath, index=False)
    pd.DataFrame(l_rows).to_parquet(lpath, index=False)

    scored, _, trained = run_ml_pipeline(
        features_path=fpath,
        regime_path=rpath,
        signals_path=spath,
        labels_path=lpath,
    )
    assert "ml_score" in scored.columns
    assert "threshold" in scored.columns
    assert "pass_filter" in scored.columns
    assert 0.2 <= trained.threshold <= 0.8
