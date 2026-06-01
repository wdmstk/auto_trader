from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from _pytest.capture import CaptureFixture
from pytest import MonkeyPatch

from auto_trader.monitor.cli import main


def test_monitor_cli_once(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    runtime_state = tmp_path / "runtime" / "control_state.json"
    runtime_state.parent.mkdir(parents=True, exist_ok=True)
    runtime_state.write_text(
        json.dumps(
            {
                "trading_enabled": True,
                "emergency_stop": False,
            }
        ),
        encoding="utf-8",
    )
    gateway_state = tmp_path / "exchange" / "gateway_state.json"
    gateway_state.parent.mkdir(parents=True, exist_ok=True)
    gateway_state.write_text(
        json.dumps({"pending_orders": {"cid-1": {"status": "pending_submit"}}}),
        encoding="utf-8",
    )
    risk_eval = tmp_path / "risk" / "risk_eval.parquet"
    risk_eval.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "blocked": True,
                "current_dd_pct": 2.5,
                "portfolio_exposure_pct": 10.0,
            }
        ]
    ).to_parquet(risk_eval, index=False)

    order_events = tmp_path / "exchange" / "order_events.jsonl"
    order_events.write_text(
        "\n".join(
            [
                json.dumps({"latency_ms": 10}),
                json.dumps({"latency_ms": 20}),
                json.dumps({"latency_ms": 30}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    out_jsonl = tmp_path / "validation" / "runtime_metrics.jsonl"

    monkeypatch.setattr(
        "sys.argv",
        [
            "monitor",
            "--runtime-state-path",
            str(runtime_state),
            "--gateway-state-path",
            str(gateway_state),
            "--risk-eval-path",
            str(risk_eval),
            "--order-events-path",
            str(order_events),
            "--output-jsonl",
            str(out_jsonl),
        ],
    )
    rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    row = json.loads(captured.out.strip())
    assert row["runtime_trading_enabled"] is True
    assert row["gateway_pending_orders"] == 1
    assert row["risk_block_count"] == 1
    assert out_jsonl.exists()


def test_monitor_cli_backlog_excludes_retry_exhausted(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    runtime_state = tmp_path / "runtime" / "control_state.json"
    runtime_state.parent.mkdir(parents=True, exist_ok=True)
    runtime_state.write_text(
        json.dumps({"trading_enabled": True, "emergency_stop": False}),
        encoding="utf-8",
    )
    gateway_state = tmp_path / "exchange" / "gateway_state.json"
    gateway_state.parent.mkdir(parents=True, exist_ok=True)
    gateway_state.write_text(
        json.dumps(
            {
                "pending_orders": {
                    "cid-a": {"status": "retry_exhausted"},
                    "cid-b": {"status": "UNKNOWN"},
                    "cid-c": {"status": "pending_submit"},
                }
            }
        ),
        encoding="utf-8",
    )
    risk_eval = tmp_path / "risk" / "risk_eval.parquet"
    risk_eval.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"blocked": False}]).to_parquet(risk_eval, index=False)
    order_events = tmp_path / "exchange" / "order_events.jsonl"
    order_events.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "monitor",
            "--runtime-state-path",
            str(runtime_state),
            "--gateway-state-path",
            str(gateway_state),
            "--risk-eval-path",
            str(risk_eval),
            "--order-events-path",
            str(order_events),
        ],
    )
    rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    row = json.loads(captured.out.strip())
    assert row["gateway_pending_orders"] == 1
