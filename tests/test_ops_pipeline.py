from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from auto_trader.ops.pipeline import run_alert_pipeline


def _prepare_inputs(tmp_path: Path) -> tuple[Path, Path]:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    runtime_path = tmp_path / "runtime" / "control_state.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        json.dumps(
            {
                "trading_enabled": False,
                "emergency_stop": True,
                "close_all_requested": True,
                "updated_at": now.isoformat(),
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    risk_path = tmp_path / "risk" / "risk_eval.parquet"
    risk_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "timestamp": now,
                "symbol": "BTCUSDT",
                "risk_blocked": True,
                "block_reason_codes": ["RISK_EMERGENCY_STOP"],
                "current_dd_pct": 20.0,
                "portfolio_exposure_pct": 10.0,
                "concentration_score": 0.2,
                "emergency_state": True,
            }
        ]
    ).to_parquet(risk_path, index=False)
    return runtime_path, risk_path


def test_run_alert_pipeline_saves_parquet_and_jsonl(tmp_path: Path) -> None:
    runtime_path, risk_path = _prepare_inputs(tmp_path)
    out_df, parquet_path, jsonl_path = run_alert_pipeline(
        runtime_state_path=runtime_path,
        risk_eval_path=risk_path,
        output_dir=tmp_path / "ops",
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert not out_df.empty
    assert parquet_path.exists()
    assert jsonl_path.exists()

    loaded = pd.read_parquet(parquet_path)
    assert len(loaded) == len(out_df)
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(out_df)
