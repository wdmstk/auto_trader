from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.stress.pipeline import run_stress_tests


def test_run_stress_tests_outputs_comparison(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    o_rows: list[dict[str, object]] = []
    s_rows: list[dict[str, object]] = []
    m_rows: list[dict[str, object]] = []
    for i in range(80):
        ts = base + timedelta(minutes=i)
        px = 100 + i * 0.05
        o_rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "open": px,
                "high": px + 0.4,
                "low": px - 0.4,
                "close": px,
                "volume": 500 + i,
            }
        )
        s_rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "entry_signal": i == 10,
                "exit_signal": i == 30,
                "regime": "RANGE" if i < 60 else "HIGH_VOL",
            }
        )
        m_rows.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "pass_filter": True,
            }
        )
    o_path = tmp_path / "ohlcv.parquet"
    s_path = tmp_path / "signals.parquet"
    m_path = tmp_path / "ml.parquet"
    pd.DataFrame(o_rows).to_parquet(o_path, index=False)
    pd.DataFrame(s_rows).to_parquet(s_path, index=False)
    pd.DataFrame(m_rows).to_parquet(m_path, index=False)

    results, compare = run_stress_tests(
        ohlcv_path=o_path,
        signals_path=s_path,
        ml_path=m_path,
    )
    assert "baseline" in set(results["scenario_name"])
    assert len(results) == 8  # baseline + 7 scenarios
    assert {"baseline_metric", "stressed_value", "degradation_pct"}.issubset(compare.columns)
    assert (results["failure_count"] >= 0).all()
