from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pytest

from auto_trader.e2e.smoke import run_e2e_smoke


def _write_inputs(
    base: Path,
    *,
    regime: str = "RANGE",
    pass_filter: bool = True,
    risk_blocked: bool = False,
    emergency_stop: bool = False,
    trading_enabled: bool = True,
) -> tuple[Path, Path, Path]:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    signals = base / "signals.parquet"
    risk = base / "risk.parquet"
    runtime = base / "runtime.json"
    pd.DataFrame(
        [
            {
                "symbol": "BTCUSDT",
                "timestamp": ts,
                "entry_signal": True,
                "pass_filter": pass_filter,
                "regime": regime,
            }
        ]
    ).to_parquet(signals, index=False)
    pd.DataFrame([{"timestamp": ts, "risk_blocked": risk_blocked}]).to_parquet(risk, index=False)
    runtime.write_text(
        json.dumps(
            {
                "trading_enabled": trading_enabled,
                "emergency_stop": emergency_stop,
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    return signals, risk, runtime


def test_e2e_smoke_pass(tmp_path: Path) -> None:
    signals, risk, runtime = _write_inputs(tmp_path)
    out = run_e2e_smoke(
        signals_path=signals,
        risk_eval_path=risk,
        runtime_state_path=runtime,
        output_dir=tmp_path / "e2e",
    )
    assert out["overall_status"] == "pass"


def test_e2e_smoke_pass_for_trend_regime_when_filter_true(tmp_path: Path) -> None:
    signals, risk, runtime = _write_inputs(tmp_path, regime="TREND", pass_filter=True)
    out = run_e2e_smoke(
        signals_path=signals,
        risk_eval_path=risk,
        runtime_state_path=runtime,
        output_dir=tmp_path / "e2e",
    )
    assert out["overall_status"] == "pass"


def test_e2e_smoke_blocks_on_high_vol(tmp_path: Path) -> None:
    signals, risk, runtime = _write_inputs(tmp_path, regime="HIGH_VOL")
    out = run_e2e_smoke(
        signals_path=signals,
        risk_eval_path=risk,
        runtime_state_path=runtime,
        output_dir=tmp_path / "e2e",
    )
    assert out["overall_status"] == "fail"
    stages = cast(list[dict[str, Any]], out["stages"])
    order_stage = [s for s in stages if s["stage"] == "order_gate_check"][0]
    assert order_stage["error_reason"] == "high_vol_blocked"


def test_e2e_smoke_blocks_on_pass_filter_false_for_trend(tmp_path: Path) -> None:
    signals, risk, runtime = _write_inputs(tmp_path, regime="TREND", pass_filter=False)
    out = run_e2e_smoke(
        signals_path=signals,
        risk_eval_path=risk,
        runtime_state_path=runtime,
        output_dir=tmp_path / "e2e",
    )
    assert out["overall_status"] == "fail"
    stages = cast(list[dict[str, Any]], out["stages"])
    order_stage = [s for s in stages if s["stage"] == "order_gate_check"][0]
    assert order_stage["error_reason"] == "pass_filter_blocked"


def test_e2e_smoke_blocks_on_runtime_emergency(tmp_path: Path) -> None:
    signals, risk, runtime = _write_inputs(tmp_path, emergency_stop=True)
    out = run_e2e_smoke(
        signals_path=signals,
        risk_eval_path=risk,
        runtime_state_path=runtime,
        output_dir=tmp_path / "e2e",
    )
    assert out["overall_status"] == "fail"
    stages = cast(list[dict[str, Any]], out["stages"])
    order_stage = [s for s in stages if s["stage"] == "order_gate_check"][0]
    assert order_stage["error_reason"] == "runtime_emergency_stop"


pytestmark = pytest.mark.smoke
