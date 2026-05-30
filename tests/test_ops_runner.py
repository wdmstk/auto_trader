from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from auto_trader.ops.runner import run_alert_watch


def test_run_alert_watch_saves_outputs(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    runtime = tmp_path / "runtime" / "control_state.json"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(
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
    risk = tmp_path / "risk" / "risk_eval.parquet"
    risk.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "timestamp": now,
                "symbol": "BTCUSDT",
                "risk_blocked": True,
                "block_reason_codes": ["RISK_EMERGENCY_STOP"],
                "current_dd_pct": 10.0,
                "portfolio_exposure_pct": 10.0,
                "concentration_score": 0.2,
                "emergency_state": True,
            }
        ]
    ).to_parquet(risk, index=False)

    out_dir = tmp_path / "ops"
    count = run_alert_watch(
        runtime_state_path=runtime,
        risk_eval_path=risk,
        output_dir=out_dir,
        interval_sec=0.1,
        max_iterations=1,
    )
    assert count == 1
    assert (out_dir / "alerts.parquet").exists()
    assert (out_dir / "alerts.jsonl").exists()
