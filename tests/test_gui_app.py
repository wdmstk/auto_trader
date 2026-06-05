from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.gui.app import (
    _active_worker_symbols,
    _candidate_best_by_symbol,
    _candidate_frame,
    _format_age,
    _freshness_level,
    _live_pnl_frame,
    _live_pnl_summary,
    _load_regime_snapshot,
    _load_symbol_regime,
    _read_latest_jsonl_row,
    _regime_mix_label,
    _runtime_health_messages,
    _status_banner,
    _strategy_symbol_table,
    _worker_last_results_frame,
    _worker_status_reason,
)
from auto_trader.worker.state import WorkerState


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


def test_format_age_and_freshness_level() -> None:
    now = datetime(2026, 6, 4, tzinfo=UTC)
    assert _format_age(now - timedelta(seconds=12), now=now) == "12s"
    assert _format_age(now - timedelta(seconds=90), now=now) == "1.5m"
    assert _freshness_level(now - timedelta(seconds=10), now=now) == "ok"
    assert _freshness_level(now - timedelta(seconds=40), now=now) == "warning"
    assert _freshness_level(now - timedelta(seconds=200), now=now) == "critical"


def test_worker_last_results_frame_and_reason() -> None:
    worker_state = WorkerState(
        last_results={
            "ETHUSDT": {
                "status": "already_processed",
                "risk_blocked": False,
                "signal": {"entry_signal": False, "reason_codes": ["TR_BLOCK_HIGH_VOL"]},
                "trade": {"status": "no_action", "gateway_status": "", "gateway_reason": ""},
            }
        }
    )
    frame = _worker_last_results_frame(worker_state)
    assert not frame.empty
    row = frame.iloc[0].to_dict()
    assert _worker_status_reason(row) == "同一確定足を処理済み"
    assert row["reason_codes"] == "TR_BLOCK_HIGH_VOL"


def test_status_banner_ignores_control_state_age() -> None:
    now = datetime.now(UTC).isoformat()
    level, messages = _status_banner(
        runtime_state={
            "trading_enabled": True,
            "emergency_stop": False,
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
        worker_state=WorkerState(updated_at=now),
        latest_metrics={
            "timestamp": now,
            "runtime_trading_enabled": True,
            "runtime_emergency_stop": False,
        },
        risk_df=pd.DataFrame([{"timestamp": now}]),
        risk_input_df=pd.DataFrame([{"timestamp": now}]),
    )
    assert level == "ok"
    assert all("Runtime state" not in message for message in messages)


def test_regime_snapshot_and_mix_label(tmp_path: Path) -> None:
    regime_dir = tmp_path / "regime"
    regime_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"timestamp": "2026-06-04T00:00:00+00:00", "regime": "RANGE"},
            {"timestamp": "2026-06-04T00:01:00+00:00", "regime": "TREND"},
        ]
    ).to_parquet(regime_dir / "ETHUSDT_1m_regime.parquet", index=False)
    pd.DataFrame(
        [
            {"timestamp": "2026-06-04T00:00:00+00:00", "regime": "HIGH_VOL"},
        ]
    ).to_parquet(regime_dir / "XRPUSDT_1m_regime.parquet", index=False)

    snapshot = _load_regime_snapshot(regime_dir)
    assert not snapshot.empty
    assert set(snapshot["symbol"]) == {"ETHUSDT", "XRPUSDT"}
    assert set(snapshot["timeframe"]) == {"1m"}
    assert _regime_mix_label(snapshot) == "HIGH_VOL MIX"


def test_load_symbol_regime_prefers_requested_timeframe(tmp_path: Path) -> None:
    regime_dir = tmp_path / "regime"
    regime_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"timestamp": "2026-06-04T00:00:00+00:00", "regime": "HIGH_VOL"},
        ]
    ).to_parquet(regime_dir / "ADAUSDT_30m_regime.parquet", index=False)
    pd.DataFrame(
        [
            {"timestamp": "2026-06-04T00:00:00+00:00", "regime": "RANGE"},
        ]
    ).to_parquet(regime_dir / "ADAUSDT_15m_regime.parquet", index=False)

    frame, timeframe = _load_symbol_regime("ADAUSDT", "15m", regime_dir=regime_dir)
    assert timeframe == "15m"
    assert not frame.empty
    assert frame.iloc[-1]["regime"] == "RANGE"


def test_live_pnl_summary_uses_market_prices(monkeypatch) -> None:
    import auto_trader.gui.app as app

    monkeypatch.setattr(
        app,
        "_latest_symbol_price",
        lambda symbol, timeframe="1m": {"ETHUSDT": 110.0, "XRPUSDT": 0.45}.get(symbol),
    )
    position_df = pd.DataFrame(
        [
            {
                "symbol": "ETHUSDT",
                "side": "buy",
                "qty": 2.0,
                "avg_entry": 100.0,
                "unrealized_pnl_pct": 0.0,
                "add_count": 0,
                "updated_at": "2026-06-04T00:00:00+00:00",
            },
            {
                "symbol": "XRPUSDT",
                "side": "sell",
                "qty": 10.0,
                "avg_entry": 0.50,
                "unrealized_pnl_pct": 0.0,
                "add_count": 0,
                "updated_at": "2026-06-04T00:00:00+00:00",
            },
        ]
    )

    frame = _live_pnl_frame(position_df)
    assert list(frame["source_price"]) == ["market", "market"]

    summary = _live_pnl_summary(position_df)
    assert round(summary["live_unrealized_pnl"], 2) == 20.50
    assert round(summary["live_unrealized_pnl_pct"], 2) == 10.00


def test_candidate_frame_and_active_worker_symbols() -> None:
    report = {
        "rows": [
            {
                "symbol": "BTCUSDT",
                "candidate_status": "watchlist",
                "strategy": "trend",
                "timeframe": "15m",
            },
            {
                "symbol": "ETHUSDT",
                "candidate_status": "core",
                "strategy": "trend",
                "timeframe": "15m",
            },
        ],
        "best_by_symbol_strategy": [
            {
                "symbol": "BTCUSDT",
                "candidate_status": "watchlist",
                "strategy": "trend",
                "timeframe": "15m",
            },
            {
                "symbol": "ETHUSDT",
                "candidate_status": "core",
                "strategy": "trend",
                "timeframe": "15m",
            },
        ],
    }
    watchlist = _candidate_frame(report, "watchlist")
    assert list(watchlist["symbol"]) == ["BTCUSDT"]
    best = _candidate_best_by_symbol(report)
    assert best["ETHUSDT"]["candidate_status"] == "core"

    worker_state = WorkerState(
        last_results={"ETHUSDT": {}, "XRPUSDT": {}},
        last_processed_bars={"trend:ADAUSDT": "2026-06-04 00:00:00+00:00"},
    )
    assert _active_worker_symbols(worker_state) == ["ADAUSDT", "ETHUSDT", "XRPUSDT"]


def test_strategy_symbol_table_uses_candidate_status_reasoning() -> None:
    candidate_rows = pd.DataFrame(
        [
            {
                "symbol": "ETHUSDT",
                "strategy": "trend",
                "timeframe": "15m",
                "candidate_status": "core",
                "pf_mean": 1.5,
                "expectancy_bps_mean": 10.0,
                "max_dd_mean": 0.05,
                "closed_trades_mean": 20,
            },
            {
                "symbol": "BTCUSDT",
                "strategy": "trend",
                "timeframe": "15m",
                "candidate_status": "watchlist",
                "pf_mean": 1.1,
                "expectancy_bps_mean": -2.0,
                "max_dd_mean": 0.10,
                "closed_trades_mean": 5,
            },
        ]
    )
    worker_state = WorkerState(
        last_results={
            "ETHUSDT": {
                "status": "already_processed",
                "signal": {
                    "entry_signal": False,
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": False,
                    "reason_codes": ["TR_ENTRY_SCORE_LOW"],
                },
                "trade": {"status": "no_action", "gateway_status": "", "gateway_reason": ""},
            }
        },
        last_processed_bars={"trend:ETHUSDT": "2026-06-04 00:00:00+00:00"},
    )
    table = _strategy_symbol_table(
        candidate_rows=candidate_rows,
        strategy="trend",
        worker_state=worker_state,
        risk_df=pd.DataFrame(),
        candidate_status_map={"ETHUSDT": "core", "BTCUSDT": "watchlist"},
    )
    core_reason = table.loc[table["symbol"] == "ETHUSDT", "why_not_trading"].iloc[0]
    watchlist_reason = table.loc[table["symbol"] == "BTCUSDT", "why_not_trading"].iloc[0]
    assert "entry未成立" in core_reason
    assert "filter未通過" in core_reason
    assert "TR_ENTRY_SCORE_LOW" in core_reason
    assert watchlist_reason == "watchlist候補"
