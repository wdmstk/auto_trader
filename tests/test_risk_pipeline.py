from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.risk.manager import RiskConfig
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


def test_run_risk_pipeline_blocks_on_correlated_exposure(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        {
            "timestamp": base,
            "symbol": "BTCUSDT",
            "current_equity": 10000.0,
            "equity_peak": 10000.0,
            "symbol_exposure_pct": 8.0,
            "portfolio_exposure_pct": 12.0,
            "concentration_score": 0.3,
            "correlated_exposure_pct": 65.0,
        }
    ]
    in_path = tmp_path / "risk_inputs.parquet"
    out_path = tmp_path / "risk_eval.parquet"
    pd.DataFrame(rows).to_parquet(in_path, index=False)

    out = run_risk_pipeline(
        input_path=in_path,
        output_path=out_path,
        config=RiskConfig(max_correlated_exposure_pct=30.0),
    )
    assert out_path.exists()
    assert bool(out.loc[0, "risk_blocked"]) is True
    reasons = out.loc[0, "block_reason_codes"]
    assert "RISK_CORRELATED_EXPOSURE" in reasons


def test_run_risk_pipeline_derives_correlated_exposure_when_missing(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        {
            "timestamp": base,
            "symbol": "BTCUSDT",
            "current_equity": 10000.0,
            "equity_peak": 10000.0,
            "symbol_exposure_pct": 40.0,
            "portfolio_exposure_pct": 60.0,
            "concentration_score": 0.7,
        },
        {
            "timestamp": base,
            "symbol": "ETHUSDT",
            "current_equity": 10000.0,
            "equity_peak": 10000.0,
            "symbol_exposure_pct": 25.0,
            "portfolio_exposure_pct": 60.0,
            "concentration_score": 0.7,
        },
        {
            "timestamp": base,
            "symbol": "XRPUSDT",
            "current_equity": 10000.0,
            "equity_peak": 10000.0,
            "symbol_exposure_pct": 10.0,
            "portfolio_exposure_pct": 60.0,
            "concentration_score": 0.7,
        },
    ]
    in_path = tmp_path / "risk_inputs.parquet"
    out_path = tmp_path / "risk_eval.parquet"
    pd.DataFrame(rows).to_parquet(in_path, index=False)

    out = run_risk_pipeline(
        input_path=in_path,
        output_path=out_path,
        config=RiskConfig(
            max_symbol_exposure_pct=100.0,
            max_portfolio_exposure_pct=100.0,
            max_concentration_score=1.0,
            max_correlated_exposure_pct=60.0,
        ),
    )
    assert "correlated_exposure_pct" in out.columns
    # top2 exposure sum at same timestamp: 40 + 25 = 65
    assert float(out.loc[0, "correlated_exposure_pct"]) == 65.0
    assert bool(out.loc[0, "risk_blocked"]) is True
    reasons = out.loc[0, "block_reason_codes"]
    assert "RISK_CORRELATED_EXPOSURE" in reasons
