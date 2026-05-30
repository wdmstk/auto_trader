from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.risk.pipeline import run_risk_pipeline


def test_run_risk_pipeline_outputs_file(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for i in range(5):
        rows.append(
            {
                "timestamp": base + timedelta(minutes=i),
                "symbol": "BTCUSDT",
                "current_equity": 10000.0 - (i * 100.0),
                "equity_peak": 10000.0,
                "symbol_exposure_pct": 8.0,
                "portfolio_exposure_pct": 12.0,
                "concentration_score": 0.3,
            }
        )
    in_path = tmp_path / "risk_inputs.parquet"
    out_path = tmp_path / "risk_eval.parquet"
    pd.DataFrame(rows).to_parquet(in_path, index=False)

    out = run_risk_pipeline(input_path=in_path, output_path=out_path)
    assert out_path.exists()
    assert "risk_blocked" in out.columns
    assert len(out) == 5
