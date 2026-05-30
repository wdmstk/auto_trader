from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pytest

from auto_trader.orchestrator.dryrun import run_dryrun_orchestration

pytestmark = pytest.mark.smoke


def _write_inputs(base: Path, *, regime: str = "RANGE") -> tuple[Path, Path, Path]:
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
                "pass_filter": True,
                "regime": regime,
            }
        ]
    ).to_parquet(signals, index=False)
    pd.DataFrame(
        [
            {
                "timestamp": ts,
                "risk_blocked": False,
                "current_dd_pct": 1.0,
            }
        ]
    ).to_parquet(risk, index=False)
    runtime.write_text(
        json.dumps({"trading_enabled": True, "emergency_stop": False}, ensure_ascii=True),
        encoding="utf-8",
    )
    return signals, risk, runtime


def test_dryrun_success_and_notify_skipped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AUTO_TRADER_NOTIFY_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("AUTO_TRADER_NOTIFY_SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("AUTO_TRADER_NOTIFY_SMTP_HOST", raising=False)
    monkeypatch.delenv("AUTO_TRADER_NOTIFY_EMAIL_FROM", raising=False)
    monkeypatch.delenv("AUTO_TRADER_NOTIFY_EMAIL_TO", raising=False)
    signals, risk, runtime = _write_inputs(tmp_path)
    out = run_dryrun_orchestration(
        signals_path=signals,
        risk_eval_path=risk,
        runtime_state_path=runtime,
        output_dir=tmp_path / "out",
    )
    assert out["overall_status"] == "pass"
    steps = cast(list[dict[str, Any]], out["steps"])
    notify_step = [s for s in steps if s["step"] == "notify_test"][0]
    assert bool(notify_step["details"]["skipped"]) is True


def test_dryrun_fail_fast_on_e2e_failure(tmp_path: Path) -> None:
    signals, risk, runtime = _write_inputs(tmp_path, regime="HIGH_VOL")
    out = run_dryrun_orchestration(
        signals_path=signals,
        risk_eval_path=risk,
        runtime_state_path=runtime,
        output_dir=tmp_path / "out",
    )
    assert out["overall_status"] == "fail"
    steps = cast(list[dict[str, Any]], out["steps"])
    assert len(steps) == 1
    assert steps[0]["step"] == "e2e_smoke"
