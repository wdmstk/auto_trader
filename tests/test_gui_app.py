from __future__ import annotations

from pathlib import Path

from auto_trader.gui.app import _read_latest_jsonl_row, _runtime_health_messages


def test_read_latest_jsonl_row_reads_last_valid_record(tmp_path: Path) -> None:
    p = tmp_path / "runtime_metrics.jsonl"
    p.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-06-01T00:00:00+00:00","gateway_pending_orders":1}',
                "invalid-json-line",
                '{"timestamp":"2026-06-01T00:01:00+00:00","gateway_pending_orders":2}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    row = _read_latest_jsonl_row(p)
    assert row["gateway_pending_orders"] == 2


def test_read_latest_jsonl_row_empty_when_missing(tmp_path: Path) -> None:
    row = _read_latest_jsonl_row(tmp_path / "missing.jsonl")
    assert row == {}


def test_runtime_health_messages_ok() -> None:
    level, messages = _runtime_health_messages(
        {
            "runtime_emergency_stop": False,
            "runtime_trading_enabled": True,
            "gateway_pending_orders": 0,
            "order_latency_p95_ms": 120,
            "risk_block_count": 0,
            "system_loadavg_1m": 0.6,
        }
    )
    assert level == "ok"
    assert any("normal ranges" in m for m in messages)


def test_runtime_health_messages_critical() -> None:
    level, messages = _runtime_health_messages(
        {
            "runtime_emergency_stop": True,
            "runtime_trading_enabled": False,
            "gateway_pending_orders": 12,
            "order_latency_p95_ms": 3000,
            "risk_block_count": 20,
            "system_loadavg_1m": 9.1,
        }
    )
    assert level == "critical"
    assert any("EMERGENCY_STOP" in m for m in messages)
