from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.ops.alerts import AlertThresholds, evaluate_alerts


def _write_runtime(path: Path, *, updated_at: datetime, emergency_stop: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "trading_enabled": not emergency_stop,
                "emergency_stop": emergency_stop,
                "close_all_requested": emergency_stop,
                "updated_at": updated_at.isoformat(),
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )


def _write_risk(path: Path, *, ts: datetime, dd_pct: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "timestamp": ts,
                "symbol": "BTCUSDT",
                "risk_blocked": dd_pct > 15.0,
                "block_reason_codes": ["RISK_OK"],
                "current_dd_pct": dd_pct,
                "portfolio_exposure_pct": 10.0,
                "concentration_score": 0.2,
                "emergency_state": False,
            }
        ]
    ).to_parquet(path, index=False)


def _codes(alerts: list[dict[str, str]]) -> set[str]:
    return {a["alert_code"] for a in alerts}


def test_evaluate_alerts_detects_stale_and_dd_and_emergency(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, 0, 10, tzinfo=UTC)
    runtime = tmp_path / "runtime.json"
    risk = tmp_path / "risk.parquet"
    _write_runtime(runtime, updated_at=now - timedelta(seconds=150), emergency_stop=True)
    _write_risk(risk, ts=now - timedelta(seconds=160), dd_pct=20.0)

    alerts = evaluate_alerts(
        runtime_state_path=runtime,
        risk_eval_path=risk,
        thresholds=AlertThresholds(max_dd_pct=15.0),
        now=now,
    )
    codes = _codes(alerts)
    assert "RUNTIME_STALE" in codes
    assert "RISK_DATA_STALE" in codes
    assert "RISK_DD_BREACH" in codes
    assert "EMERGENCY_ACTIVE" in codes


def test_evaluate_alerts_detects_reject_spike(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, 0, 10, tzinfo=UTC)
    runtime = tmp_path / "runtime.json"
    risk = tmp_path / "risk.parquet"
    orders = tmp_path / "orders.parquet"
    _write_runtime(runtime, updated_at=now, emergency_stop=False)
    _write_risk(risk, ts=now, dd_pct=1.0)
    pd.DataFrame([{"status": "rejected"}, {"status": "rejected"}, {"status": "ack"}]).to_parquet(
        orders, index=False
    )

    alerts = evaluate_alerts(
        runtime_state_path=runtime,
        risk_eval_path=risk,
        order_events_path=orders,
        thresholds=AlertThresholds(reject_rate_warn=0.2),
        now=now,
    )
    assert "ORDER_REJECT_SPIKE" in _codes(alerts)


def test_evaluate_alerts_contract_fields_present(tmp_path: Path) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    runtime = tmp_path / "runtime.json"
    risk = tmp_path / "risk.parquet"
    _write_runtime(runtime, updated_at=now - timedelta(seconds=40), emergency_stop=False)
    _write_risk(risk, ts=now - timedelta(seconds=40), dd_pct=1.0)

    alerts = evaluate_alerts(runtime_state_path=runtime, risk_eval_path=risk, now=now)
    assert alerts
    required = {"alert_code", "severity", "detected_at", "source", "summary", "action_required"}
    for row in alerts:
        assert required.issubset(row.keys())
