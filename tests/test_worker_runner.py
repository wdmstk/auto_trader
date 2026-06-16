# Dynamic cycle summaries are intentionally asserted as nested JSON-like objects.
# mypy: disable-error-code="no-untyped-def,method-assign,index,call-overload,union-attr,operator"

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from auto_trader.position.models import PositionState, build_route_key
from auto_trader.worker.runner import LiveTradingWorker, WorkerConfig


class DummyTransport:
    def __init__(self) -> None:
        self.calls = 0

    def send_order(self, order):
        self.calls += 1
        return True, f"ord_{self.calls:06d}", "accepted"

    def normalize_order_request(self, order):
        return order


def _runtime_state(
    path: Path,
    *,
    trading_enabled: bool,
    emergency_stop: bool = False,
    close_all: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "trading_enabled": trading_enabled,
                "emergency_stop": emergency_stop,
                "close_all_requested": close_all,
                "updated_at": datetime.now(UTC).isoformat(),
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )


def _frame(ts: datetime) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": ts,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1000.0,
                "symbol": "TEST",
                "timeframe": "15m",
            }
        ]
    )


def _write_risk_input(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_settings(path: Path, *, max_symbol: float, max_portfolio: float, max_dd: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "system:",
                "  env: prod",
                "  mode: production",
                "exchange:",
                "  name: binance",
                "  margin_type: isolated",
                "  max_leverage: 1",
                "risk:",
                "  max_risk_per_trade_pct: 0.5",
                f"  max_symbol_exposure_pct: {max_symbol}",
                f"  max_portfolio_exposure_pct: {max_portfolio}",
                f"  max_drawdown_pct: {max_dd}",
                "runtime:",
                "  emergency_stop_enabled: true",
                "logging:",
                "  level: WARN",
                "  jsonl_path: logs/test.jsonl",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _worker(
    tmp_path: Path,
    transport: DummyTransport,
    *,
    execution_mode: str = "testnet",
    settings_path: str = "",
    risk_input_path: str = "",
) -> LiveTradingWorker:
    runtime_state = tmp_path / "runtime" / "control_state.json"
    positions_dir = tmp_path / "positions"
    worker = LiveTradingWorker(
        config=WorkerConfig(
            symbols=("ETHUSDT", "XRPUSDT"),
            execution_mode=execution_mode,
            trend_symbols=("ETHUSDT",),
            range_symbols=("XRPUSDT",),
            weekly_revalidation_report_path=str(tmp_path / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"),
            trend_order_mode="limit",
            range_order_mode="market",
            runtime_state_path=str(runtime_state),
            gateway_state_path=str(tmp_path / "gateway_state.json"),
            positions_dir=str(positions_dir),
            worker_state_path=str(tmp_path / "worker_state.json"),
            order_events_path=str(tmp_path / "order_events.jsonl"),
            settings_path=settings_path,
            risk_input_path=risk_input_path or str(tmp_path / "risk" / "risk_input.parquet"),
            market_limit=10,
            poll_interval_sec=0.01,
            max_iterations=1,
        ),
        transport=transport,
    )
    worker._closed_market_frame = lambda raw_frame, timeframe: raw_frame.copy().assign(timeframe=timeframe)
    return worker


def _write_weekly_report(path: Path, *, trend: list[str], range_: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "statistical_qualification": {"status": "pass"},
                "selection": {
                    "trend_enabled_symbols": trend,
                    "range_enabled_symbols": range_,
                    "timeframe": "15m",
                },
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )


def _write_weekly_route_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "statistical_qualification": {"status": "pass"},
                "selection": {
                    "trade_routes": [
                        {
                            "symbol": "BNBUSDT",
                            "strategy": "range",
                            "timeframe": "30m",
                            "expected_regime": "RANGE",
                            "candidate_status": "core",
                            "statistical_status": "pass",
                        }
                    ]
                },
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )


def _write_weekly_fail_route_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "statistical_qualification": {"status": "fail"},
                "selection": {
                    "trade_routes": [
                        {
                            "symbol": "BNBUSDT",
                            "strategy": "range",
                            "timeframe": "30m",
                            "expected_regime": "RANGE",
                            "candidate_status": "core",
                            "statistical_status": "fail",
                        }
                    ]
                },
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )


def _write_weekly_route_report_without_statistical_status(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "statistical_qualification": {"status": "pass"},
                "selection": {
                    "trade_routes": [
                        {
                            "symbol": "BNBUSDT",
                            "strategy": "range",
                            "timeframe": "30m",
                            "expected_regime": "RANGE",
                            "candidate_status": "core",
                        }
                    ]
                },
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )


def _write_weekly_route_report_without_statistical_qualification(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "selection": {
                    "trade_routes": [
                        {
                            "symbol": "BNBUSDT",
                            "strategy": "range",
                            "timeframe": "30m",
                            "expected_regime": "RANGE",
                            "candidate_status": "core",
                        }
                    ]
                },
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )


def _write_weekly_multi_route_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "statistical_qualification": {"status": "pass"},
                "selection": {
                    "trade_routes": [
                        {
                            "symbol": "XRPUSDT",
                            "strategy": "range",
                            "timeframe": "15m",
                            "expected_regime": "RANGE",
                            "candidate_status": "core",
                            "statistical_status": "pass",
                        },
                        {
                            "symbol": "XRPUSDT",
                            "strategy": "trend",
                            "timeframe": "15m",
                            "expected_regime": "TREND",
                            "candidate_status": "core",
                            "statistical_status": "pass",
                        },
                    ]
                },
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )


def _write_autotune_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source": "autotune_full_manifest",
                "selection": {
                    "trade_routes": [
                        {
                            "symbol": "SOLUSDT",
                            "strategy": "range",
                            "timeframe": "30m",
                            "expected_regime": "RANGE",
                            "candidate_status": "core",
                            "statistical_status": "pass",
                        },
                        {
                            "symbol": "ETHUSDT",
                            "strategy": "trend",
                            "timeframe": "1h",
                            "expected_regime": "TREND",
                            "candidate_status": "core",
                            "statistical_status": "pass",
                        },
                    ]
                },
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )


def test_worker_skips_new_orders_when_trading_disabled(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=False)
    ts = datetime.now(UTC).replace(microsecond=0)
    frames = {symbol: _frame(ts) for symbol in ("ETHUSDT", "XRPUSDT")}
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: frames)
    monkeypatch.setattr(
        worker,
        "_build_signal_frame",
        lambda *, symbol, frame_15m, route, timeframe: pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "TREND",
                    "entry_signal": True,
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"],
                    "position_size_ratio": 0.1,
                }
            ]
        ),
    )

    summary = worker.run_once()

    assert transport.calls == 0
    assert summary["runtime"]["trading_enabled"] is False


def test_worker_routes_entries_and_deduplicates_same_bar(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    frames = {symbol: _frame(ts) for symbol in ("ETHUSDT", "XRPUSDT")}
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: frames)

    def build_signal_frame(*, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str) -> pd.DataFrame:
        is_entry = symbol == "ETHUSDT" and route == "trend"
        return pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "TREND" if route == "trend" else "RANGE",
                    "entry_signal": is_entry,
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"] if is_entry else [],
                    "position_size_ratio": 0.1,
                }
            ]
        )

    monkeypatch.setattr(worker, "_build_signal_frame", build_signal_frame)

    first = worker.run_once()
    second = worker.run_once()

    assert transport.calls == 1
    route_key = build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")
    assert first["routes"][route_key]["trade"]["gateway_status"] == "ack"
    assert second["routes"][route_key]["status"] == "already_processed"
    state = json.loads((tmp_path / "worker_state.json").read_text(encoding="utf-8"))
    assert state["last_processed_bars"]["trend:ETHUSDT:15m"] == str(pd.to_datetime(ts, utc=True))


def test_worker_emergency_stop_can_flatten_positions(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    _runtime_state(
        tmp_path / "runtime" / "control_state.json",
        trading_enabled=False,
        emergency_stop=True,
        close_all=True,
    )
    worker.position_manager.replace_positions(
        [
            PositionState(
                symbol="ETHUSDT",
                side="buy",
                qty=0.5,
                avg_entry=100.0,
                unrealized_pnl_pct=0.0,
                add_count=0,
                updated_at=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
            )
        ]
    )
    ts = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: {"ETHUSDT": _frame(ts)})

    summary = worker.run_once()

    assert transport.calls == 1
    assert summary["orders"][0]["status"] == "ack"
    assert summary["orders"][0]["pending_reconciliation"] is True
    assert worker.position_manager.get(build_route_key(strategy="legacy", symbol="ETHUSDT", timeframe="15m")).qty == 0.5


def test_worker_allows_exit_when_high_vol_blocks_entries(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    route_key = build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")
    worker.position_manager.replace_positions(
        [
            PositionState(
                symbol="ETHUSDT",
                side="buy",
                qty=0.5,
                avg_entry=100.0,
                unrealized_pnl_pct=-0.01,
                add_count=0,
                updated_at=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
                strategy="trend",
                timeframe="15m",
                route_key=route_key,
            )
        ]
    )
    ts = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: {"ETHUSDT": _frame(ts)})

    def build_signal_frame(*, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "HIGH_VOL",
                    "entry_signal": False,
                    "exit_signal": True,
                    "add_signal": False,
                    "pass_filter": False,
                    "signal_reason_codes": ["TR_BLOCK_HIGH_VOL", "TR_EXIT_REGIME_CHANGED"],
                    "position_size_ratio": 0.1,
                }
            ]
        )

    monkeypatch.setattr(worker, "_build_signal_frame", build_signal_frame)

    summary = worker.run_once()

    assert transport.calls == 1
    assert summary["orders"][0]["action"] == "exit"
    assert summary["orders"][0]["status"] == "ack"
    assert summary["orders"][0]["regime"] == "HIGH_VOL"
    assert summary["orders"][0]["pending_reconciliation"] is True


def test_worker_refreshes_symbols_from_weekly_report(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    weekly_path = tmp_path / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"
    _write_weekly_report(weekly_path, trend=["ADAUSDT"], range_=["BNBUSDT"])
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    frames = {symbol: _frame(ts) for symbol in ("ETHUSDT", "ADAUSDT", "BNBUSDT")}
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: frames)

    def build_signal_frame(*, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str) -> pd.DataFrame:
        is_entry = (symbol == "ADAUSDT" and route == "trend") or (symbol == "BNBUSDT" and route == "range")
        return pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "TREND" if route == "trend" else "RANGE",
                    "entry_signal": is_entry,
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"] if is_entry else [],
                    "position_size_ratio": 0.1,
                }
            ]
        )

    monkeypatch.setattr(worker, "_build_signal_frame", build_signal_frame)

    summary = worker.run_once()

    assert summary["symbol_sync"]["status"] == "updated"
    assert summary["trade_symbols"]["trend_symbols"] == ["ADAUSDT"]
    assert summary["trade_symbols"]["range_symbols"] == ["BNBUSDT"]
    assert set(summary["symbols"]) == {"ADAUSDT", "BNBUSDT"}
    assert transport.calls == 2


def test_worker_refreshes_trade_routes_with_timeframe(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    weekly_path = tmp_path / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"
    _write_weekly_route_report(weekly_path)
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    frames = {symbol: _frame(ts) for symbol in ("ETHUSDT", "XRPUSDT", "BNBUSDT")}
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: frames)

    def build_signal_frame(*, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str) -> pd.DataFrame:
        is_entry = symbol == "BNBUSDT" and route == "range" and timeframe == "30m"
        return pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "RANGE" if timeframe == "30m" else "TREND",
                    "entry_signal": is_entry,
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"] if is_entry else [],
                    "position_size_ratio": 0.1,
                }
            ]
        )

    monkeypatch.setattr(worker, "_build_signal_frame", build_signal_frame)

    summary = worker.run_once()

    assert summary["symbol_sync"]["status"] == "updated"
    assert summary["trade_symbols"]["trade_routes"][0]["timeframe"] == "30m"
    assert summary["trade_symbols"]["range_symbols"] == ["BNBUSDT"]
    route_key = build_route_key(strategy="range", symbol="BNBUSDT", timeframe="30m")
    assert summary["routes"][route_key]["route"]["timeframe"] == "30m"
    assert summary["routes"][route_key]["signal"]["timeframe"] == "30m"
    assert summary["routes"][route_key]["trade"]["gateway_status"] == "ack"
    assert transport.calls == 1
    state = json.loads((tmp_path / "worker_state.json").read_text(encoding="utf-8"))
    assert state["last_processed_bars"]["range:BNBUSDT:30m"] == str(pd.to_datetime(ts, utc=True))


def test_worker_testnet_keeps_statistical_fail_routes_with_warning(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    weekly_path = tmp_path / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"
    _write_weekly_fail_route_report(weekly_path)
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    frames = {symbol: _frame(ts) for symbol in ("ETHUSDT", "XRPUSDT", "BNBUSDT")}
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: frames)

    monkeypatch.setattr(
        worker,
        "_build_signal_frame",
        lambda *, symbol, frame_15m, route, timeframe: pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "RANGE" if timeframe == "30m" else "TREND",
                    "entry_signal": symbol == "BNBUSDT" and route == "range" and timeframe == "30m",
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"] if symbol == "BNBUSDT" else [],
                    "position_size_ratio": 0.1,
                }
            ]
        ),
    )

    summary = worker.run_once()

    route_key = build_route_key(strategy="range", symbol="BNBUSDT", timeframe="30m")
    assert summary["symbol_sync"]["status"] == "updated"
    assert route_key in summary["routes"]
    assert summary["trade_symbols"]["trade_routes"][0]["statistical_status"] == "fail"
    assert summary["trade_symbols"]["trade_routes"][0]["route_policy"] == "test-only / statistical-fail"
    assert summary["routes"][route_key]["trade"]["gateway_status"] == "ack"


def test_worker_production_rejects_fail_route_selection(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    settings_path = tmp_path / "config.prod.yaml"
    _write_settings(settings_path, max_symbol=8.0, max_portfolio=25.0, max_dd=8.0)
    worker = _worker(
        tmp_path,
        transport,
        execution_mode="production",
        settings_path=str(settings_path),
    )
    weekly_path = tmp_path / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"
    _write_weekly_fail_route_report(weekly_path)
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    frames = {symbol: _frame(ts) for symbol in ("ETHUSDT", "XRPUSDT", "BNBUSDT")}
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: frames)

    monkeypatch.setattr(
        worker,
        "_build_signal_frame",
        lambda *, symbol, frame_15m, route, timeframe: pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "RANGE" if timeframe == "30m" else "TREND",
                    "entry_signal": symbol == "BNBUSDT" and route == "range" and timeframe == "30m",
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"] if symbol == "BNBUSDT" else [],
                    "position_size_ratio": 0.1,
                }
            ]
        ),
    )

    summary = worker.run_once()

    assert summary["symbol_sync"]["status"] == "updated"
    assert summary["symbol_sync"]["execution_mode"] == "production"
    assert summary["trade_symbols"]["trade_routes"] == []
    assert summary["routes"] == {}
    assert transport.calls == 0


def test_worker_gateway_runtime_policy_depends_on_execution_mode(tmp_path: Path) -> None:
    transport = DummyTransport()
    settings_path = tmp_path / "config.prod.yaml"
    _write_settings(settings_path, max_symbol=8.0, max_portfolio=25.0, max_dd=8.0)
    production_worker = _worker(
        tmp_path,
        transport,
        execution_mode="production",
        settings_path=str(settings_path),
    )
    assert production_worker.gateway.config.require_runtime_state is True
    assert production_worker.gateway.config.allow_runtime_state_fail_open is False
    assert production_worker.gateway.config.runtime_state_max_age_sec == 120

    dryrun_worker = LiveTradingWorker(
        config=WorkerConfig(
            symbols=("ETHUSDT",),
            trend_symbols=("ETHUSDT",),
            range_symbols=(),
            execution_mode="dry-run",
            runtime_state_path=str(tmp_path / "runtime" / "control_state.json"),
            gateway_state_path=str(tmp_path / "gateway_state_dryrun.json"),
            positions_dir=str(tmp_path / "positions_dryrun"),
            worker_state_path=str(tmp_path / "worker_state_dryrun.json"),
            order_events_path=str(tmp_path / "order_events_dryrun.jsonl"),
            allow_runtime_state_fail_open=True,
            runtime_state_max_age_sec=45,
            settings_path="",
        ),
        transport=transport,
    )
    assert dryrun_worker.gateway.config.require_runtime_state is False
    assert dryrun_worker.gateway.config.allow_runtime_state_fail_open is True
    assert dryrun_worker.gateway.config.runtime_state_max_age_sec == 45


def test_worker_uses_production_risk_config_as_single_source(tmp_path: Path) -> None:
    transport = DummyTransport()
    settings_path = tmp_path / "config.prod.yaml"
    _write_settings(settings_path, max_symbol=8.0, max_portfolio=25.0, max_dd=8.0)
    worker = _worker(
        tmp_path,
        transport,
        execution_mode="production",
        settings_path=str(settings_path),
    )

    assert worker.position_manager.config.max_symbol_exposure_pct == 8.0
    assert worker.position_manager.config.max_portfolio_exposure_pct == 25.0
    assert worker._risk_manager.config.max_dd_pct == 8.0
    assert worker._effective_risk_config.source_path == str(settings_path)


def test_worker_keeps_previous_symbols_when_weekly_report_is_broken(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    weekly_path = tmp_path / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"
    _write_weekly_report(weekly_path, trend=["ADAUSDT"], range_=["BNBUSDT"])
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts1 = datetime.now(UTC).replace(microsecond=0)
    frames1 = {symbol: _frame(ts1) for symbol in ("ETHUSDT", "ADAUSDT", "BNBUSDT")}
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: frames1)

    def build_signal_frame(*, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str) -> pd.DataFrame:
        is_entry = symbol == "BNBUSDT" and route == "range"
        return pd.DataFrame(
            [
                {
                    "timestamp": ts1,
                    "regime": "RANGE",
                    "entry_signal": is_entry,
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"] if is_entry else [],
                    "position_size_ratio": 0.1,
                }
            ]
        )

    monkeypatch.setattr(worker, "_build_signal_frame", build_signal_frame)
    first = worker.run_once()
    assert first["trade_symbols"]["range_symbols"] == ["BNBUSDT"]

    weekly_path.write_text("{broken", encoding="utf-8")
    ts2 = ts1.replace(minute=(ts1.minute + 1) % 60)
    frames2 = {symbol: _frame(ts2) for symbol in ("ETHUSDT", "ADAUSDT", "BNBUSDT")}
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: frames2)

    def build_signal_frame_second(*, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str) -> pd.DataFrame:
        is_exit = symbol == "BNBUSDT" and route == "range"
        return pd.DataFrame(
            [
                {
                    "timestamp": ts2,
                    "regime": "RANGE",
                    "entry_signal": False,
                    "exit_signal": is_exit,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["EXIT_OK"] if is_exit else [],
                    "position_size_ratio": 0.1,
                }
            ]
        )

    monkeypatch.setattr(worker, "_build_signal_frame", build_signal_frame_second)

    second = worker.run_once()

    assert second["symbol_sync"]["status"] == "missing_or_invalid"
    assert second["trade_symbols"]["range_symbols"] == ["BNBUSDT"]
    assert "BNBUSDT" in second["symbols"]
    assert transport.calls == 1


def test_worker_supports_multiple_routes_for_same_symbol(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    weekly_path = tmp_path / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"
    _write_weekly_multi_route_report(weekly_path)
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: {"XRPUSDT": _frame(ts)})

    def build_signal_frame(*, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "TREND" if route == "trend" else "RANGE",
                    "entry_signal": True,
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"],
                    "position_size_ratio": 0.1,
                }
            ]
        )

    monkeypatch.setattr(worker, "_build_signal_frame", build_signal_frame)

    summary = worker.run_once()

    range_key = build_route_key(strategy="range", symbol="XRPUSDT", timeframe="15m")
    trend_key = build_route_key(strategy="trend", symbol="XRPUSDT", timeframe="15m")
    assert summary["symbol_sync"]["status"] == "updated"
    assert set(summary["routes"]) == {range_key, trend_key}
    assert transport.calls == 2
    assert worker.position_manager.get(range_key) is None
    assert worker.position_manager.get(trend_key) is None


def test_worker_refreshes_routes_from_autotune_manifest_path(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    manifest_path = tmp_path / "validation" / "core_route_autotune" / "autotune_full_route_manifest.json"
    _write_autotune_manifest(manifest_path)
    _write_weekly_report(
        tmp_path / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json",
        trend=["ADAUSDT"],
        range_=["BNBUSDT"],
    )
    worker.config = WorkerConfig(
        **{
            **worker.config.__dict__,
            "route_selection_path": str(manifest_path),
        }
    )
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(
        worker,
        "_load_closed_market_frames",
        lambda: {"SOLUSDT": _frame(ts), "ETHUSDT": _frame(ts)},
    )

    def build_signal_frame(*, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str) -> pd.DataFrame:
        is_entry = (symbol, route, timeframe) in {
            ("SOLUSDT", "range", "30m"),
            ("ETHUSDT", "trend", "1h"),
        }
        return pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "TREND" if route == "trend" else "RANGE",
                    "entry_signal": is_entry,
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"] if is_entry else [],
                    "position_size_ratio": 0.1,
                }
            ]
        )

    monkeypatch.setattr(worker, "_build_signal_frame", build_signal_frame)

    summary = worker.run_once()

    assert summary["symbol_sync"]["status"] == "updated"
    assert summary["symbol_sync"]["selection_path"] == str(manifest_path)
    assert summary["trade_symbols"]["range_symbols"] == ["SOLUSDT"]
    assert summary["trade_symbols"]["trend_symbols"] == ["ETHUSDT"]
    assert {route["timeframe"] for route in summary["trade_symbols"]["trade_routes"]} == {
        "30m",
        "1h",
    }
    assert transport.calls == 2


def test_worker_logs_normalized_order_values(tmp_path: Path, monkeypatch) -> None:
    class PrecisionTransport(DummyTransport):
        def normalize_order_request(self, order):
            return type(order)(
                **{
                    **order.__dict__,
                    "qty": 100.0,
                    "limit_price": 0.12,
                }
            )

    transport = PrecisionTransport()
    worker = _worker(tmp_path, transport)
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: {"ETHUSDT": _frame(ts)})

    def build_signal_frame(*, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "TREND",
                    "entry_signal": True,
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"],
                    "position_size_ratio": 0.1,
                }
            ]
        )

    monkeypatch.setattr(worker, "_build_signal_frame", build_signal_frame)
    worker._active_routes = {
        build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m"): worker._active_routes[
            build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")
        ]
    }
    worker._active_symbols = ("ETHUSDT",)
    worker._active_trend_symbols = ("ETHUSDT",)
    worker._active_range_symbols = ()

    summary = worker.run_once()

    route_key = build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")
    assert summary["routes"][route_key]["trade"]["qty"] == 100.0
    assert summary["routes"][route_key]["trade"]["limit_price"] == 0.12


def test_worker_order_events_include_side_and_latency(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: {"ETHUSDT": _frame(ts)})

    monkeypatch.setattr(
        worker,
        "_build_signal_frame",
        lambda *, symbol, frame_15m, route, timeframe: pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "TREND",
                    "entry_signal": True,
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"],
                    "position_size_ratio": 0.1,
                }
            ]
        ),
    )

    worker._active_routes = {
        build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m"): worker._active_routes[
            build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")
        ]
    }
    worker._active_symbols = ("ETHUSDT",)
    worker._active_trend_symbols = ("ETHUSDT",)
    worker._active_range_symbols = ()

    worker.run_once()

    rows = (tmp_path / "order_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    payload = json.loads(rows[0])
    assert payload["side"] == "buy"
    assert isinstance(payload["latency_ms"], int)


def test_worker_reconciles_expired_limit_entry_to_flat_position(tmp_path: Path) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)

    result = worker._submit_order(
        symbol="ETHUSDT",
        side="buy",
        qty=0.5,
        order_type="limit",
        limit_price=100.0,
        signal_ts=datetime.now(UTC).replace(microsecond=0),
        regime="TREND",
        pass_filter=True,
        strategy="trend",
        timeframe="15m",
        route_key=build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m"),
        allow_runtime_gate=True,
        action="entry",
        price=100.0,
        is_add=False,
        pre_position=None,
    )

    assert result["gateway_status"] == "ack"
    assert worker.position_manager.get(build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")) is None

    execution_events = tmp_path / "execution_events.jsonl"
    execution_events.write_text(
        (
            '{"stream":"ethusdt@executionReport","data":{"E":1704067200000,'
            f'"i":"{result["order_id"]}","c":"{result["client_order_id"]}",'
            '"s":"ETHUSDT","S":"BUY","X":"EXPIRED","z":"0.0"}}\n'
        ),
        encoding="utf-8",
    )
    worker.config = WorkerConfig(
        **{
            **worker.config.__dict__,
            "execution_events_path": str(execution_events),
            "execution_cursor_path": str(tmp_path / "execution_cursor.json"),
        }
    )

    sync = worker.reconcile_execution_events_once()

    assert sync["applied"] == 1
    assert worker.position_manager.get(build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")) is None
    rows = (tmp_path / "order_events.jsonl").read_text(encoding="utf-8").splitlines()
    payload = json.loads(rows[-1])
    assert payload["sync_source"] == "execution_report"
    assert payload["status"] == "expired"
    assert payload["reconciled_position_qty"] == 0.0


def test_worker_reconciles_partial_exit_and_preserves_avg_entry(tmp_path: Path) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    route_key = build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")
    worker.position_manager.replace_positions(
        [
            PositionState(
                symbol="ETHUSDT",
                side="buy",
                qty=1.0,
                avg_entry=90.0,
                unrealized_pnl_pct=0.0,
                add_count=0,
                updated_at=datetime.now(UTC),
                strategy="trend",
                timeframe="15m",
                route_key=route_key,
            )
        ]
    )

    result = worker._submit_order(
        symbol="ETHUSDT",
        side="sell",
        qty=1.0,
        order_type="limit",
        limit_price=110.0,
        signal_ts=datetime.now(UTC).replace(microsecond=0),
        regime="TREND",
        pass_filter=True,
        strategy="trend",
        timeframe="15m",
        route_key=route_key,
        allow_runtime_gate=True,
        action="exit",
        price=110.0,
        is_add=False,
        pre_position=worker.position_manager.get(route_key),
    )

    assert result["gateway_status"] == "ack"
    assert worker.position_manager.get(route_key) is not None
    assert worker.position_manager.get(route_key).qty == 1.0

    execution_events = tmp_path / "execution_events_partial.jsonl"
    execution_events.write_text(
        (
            '{"stream":"ethusdt@executionReport","data":{"E":1704067200000,'
            f'"i":"{result["order_id"]}","c":"{result["client_order_id"]}",'
            '"s":"ETHUSDT","S":"SELL","X":"EXPIRED","z":"0.3"}}\n'
        ),
        encoding="utf-8",
    )
    worker.config = WorkerConfig(
        **{
            **worker.config.__dict__,
            "execution_events_path": str(execution_events),
            "execution_cursor_path": str(tmp_path / "execution_cursor_partial.json"),
        }
    )

    sync = worker.reconcile_execution_events_once()

    assert sync["applied"] == 1
    position = worker.position_manager.get(route_key)
    assert position is not None
    assert abs(position.qty - 0.7) < 1e-9
    assert abs(position.avg_entry - 90.0) < 1e-9


def test_worker_reconciles_partial_entry_then_full_fill_with_actual_execution_price(
    tmp_path: Path,
) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    route_key = build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")

    result = worker._submit_order(
        symbol="ETHUSDT",
        side="buy",
        qty=1.0,
        order_type="limit",
        limit_price=100.0,
        signal_ts=datetime.now(UTC).replace(microsecond=0),
        regime="TREND",
        pass_filter=True,
        strategy="trend",
        timeframe="15m",
        route_key=route_key,
        allow_runtime_gate=True,
        action="entry",
        price=100.0,
        is_add=False,
        pre_position=None,
    )

    assert result["gateway_status"] == "ack"
    assert worker.position_manager.get(route_key) is None

    execution_events = tmp_path / "execution_events_entry.jsonl"
    execution_events.write_text(
        (
            '{"stream":"ethusdt@executionReport","data":{"E":1704067200000,'
            f'"i":"{result["order_id"]}","c":"{result["client_order_id"]}",'
            '"s":"ETHUSDT","S":"BUY","X":"PARTIALLY_FILLED","z":"0.3","ap":"101.0"}}\n'
            '{"stream":"ethusdt@executionReport","data":{"E":1704067260000,'
            f'"i":"{result["order_id"]}","c":"{result["client_order_id"]}",'
            '"s":"ETHUSDT","S":"BUY","X":"FILLED","z":"1.0","ap":"102.0"}}\n'
        ),
        encoding="utf-8",
    )
    worker.config = WorkerConfig(
        **{
            **worker.config.__dict__,
            "execution_events_path": str(execution_events),
            "execution_cursor_path": str(tmp_path / "execution_cursor_entry.json"),
        }
    )

    sync = worker.reconcile_execution_events_once()

    assert sync["applied"] == 2
    position = worker.position_manager.get(route_key)
    assert position is not None
    assert abs(position.qty - 1.0) < 1e-9
    assert abs(position.avg_entry - 101.7) < 1e-9


def test_worker_ignores_duplicate_and_out_of_order_execution_events(tmp_path: Path) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    route_key = build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")

    result = worker._submit_order(
        symbol="ETHUSDT",
        side="buy",
        qty=1.0,
        order_type="limit",
        limit_price=100.0,
        signal_ts=datetime.now(UTC).replace(microsecond=0),
        regime="TREND",
        pass_filter=True,
        strategy="trend",
        timeframe="15m",
        route_key=route_key,
        allow_runtime_gate=True,
        action="entry",
        price=100.0,
        is_add=False,
        pre_position=None,
    )

    execution_events = tmp_path / "execution_events_duplicate.jsonl"
    execution_events.write_text(
        (
            '{"stream":"ethusdt@executionReport","data":{"E":1704067200000,'
            f'"i":"{result["order_id"]}","c":"{result["client_order_id"]}",'
            '"s":"ETHUSDT","S":"BUY","X":"PARTIALLY_FILLED","z":"0.4","ap":"100.0"}}\n'
            '{"stream":"ethusdt@executionReport","data":{"E":1704067200000,'
            f'"i":"{result["order_id"]}","c":"{result["client_order_id"]}",'
            '"s":"ETHUSDT","S":"BUY","X":"PARTIALLY_FILLED","z":"0.4","ap":"100.0"}}\n'
            '{"stream":"ethusdt@executionReport","data":{"E":1704067140000,'
            f'"i":"{result["order_id"]}","c":"{result["client_order_id"]}",'
            '"s":"ETHUSDT","S":"BUY","X":"PARTIALLY_FILLED","z":"0.2","ap":"99.0"}}\n'
        ),
        encoding="utf-8",
    )
    worker.config = WorkerConfig(
        **{
            **worker.config.__dict__,
            "execution_events_path": str(execution_events),
            "execution_cursor_path": str(tmp_path / "execution_cursor_duplicate.json"),
        }
    )

    sync = worker.reconcile_execution_events_once()

    assert sync["applied"] == 1
    assert sync["ignored"] == 2
    position = worker.position_manager.get(route_key)
    assert position is not None
    assert abs(position.qty - 0.4) < 1e-9


def test_worker_reconciles_remaining_fill_after_restart(tmp_path: Path) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    route_key = build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")

    result = worker._submit_order(
        symbol="ETHUSDT",
        side="buy",
        qty=1.0,
        order_type="limit",
        limit_price=100.0,
        signal_ts=datetime.now(UTC).replace(microsecond=0),
        regime="TREND",
        pass_filter=True,
        strategy="trend",
        timeframe="15m",
        route_key=route_key,
        allow_runtime_gate=True,
        action="entry",
        price=100.0,
        is_add=False,
        pre_position=None,
    )

    first_events = tmp_path / "execution_events_restart_1.jsonl"
    first_events.write_text(
        (
            '{"stream":"ethusdt@executionReport","data":{"E":1704067200000,'
            f'"i":"{result["order_id"]}","c":"{result["client_order_id"]}",'
            '"s":"ETHUSDT","S":"BUY","X":"PARTIALLY_FILLED","z":"0.25","ap":"100.0"}}\n'
        ),
        encoding="utf-8",
    )
    worker.config = WorkerConfig(
        **{
            **worker.config.__dict__,
            "execution_events_path": str(first_events),
            "execution_cursor_path": str(tmp_path / "execution_cursor_restart.json"),
        }
    )
    first_sync = worker.reconcile_execution_events_once()
    assert first_sync["applied"] == 1

    restarted = _worker(tmp_path, transport)
    second_events = tmp_path / "execution_events_restart_2.jsonl"
    second_events.write_text(
        (
            '{"stream":"ethusdt@executionReport","data":{"E":1704067260000,'
            f'"i":"{result["order_id"]}","c":"{result["client_order_id"]}",'
            '"s":"ETHUSDT","S":"BUY","X":"FILLED","z":"1.0","ap":"101.0"}}\n'
        ),
        encoding="utf-8",
    )
    restarted.config = WorkerConfig(
        **{
            **restarted.config.__dict__,
            "execution_events_path": str(second_events),
            "execution_cursor_path": str(tmp_path / "execution_cursor_restart_2.json"),
            "order_events_path": str(tmp_path / "order_events.jsonl"),
            "positions_dir": str(tmp_path / "positions"),
        }
    )

    sync = restarted.reconcile_execution_events_once()

    assert sync["applied"] == 1
    position = restarted.position_manager.get(route_key)
    assert position is not None
    assert abs(position.qty - 1.0) < 1e-9


def test_worker_blocks_entry_when_symbol_exposure_exceeds_production_limit(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    settings_path = tmp_path / "config.prod.yaml"
    _write_settings(settings_path, max_symbol=8.0, max_portfolio=25.0, max_dd=8.0)
    risk_input_path = tmp_path / "risk" / "risk_input.parquet"
    _write_risk_input(
        risk_input_path,
        [
            {
                "timestamp": datetime.now(UTC),
                "symbol": "ETHUSDT",
                "current_equity": 1000.0,
                "equity_peak": 1000.0,
                "symbol_exposure_pct": 2.0,
                "portfolio_exposure_pct": 2.0,
                "concentration_score": 1.0,
                "correlated_exposure_pct": 2.0,
                "vol_weighted_exposure_pct": 2.0,
                "risk_contribution_pct": 2.0,
                "missing_vol_ratio": 0.0,
            }
        ],
    )
    worker = _worker(
        tmp_path,
        transport,
        execution_mode="production",
        settings_path=str(settings_path),
        risk_input_path=str(risk_input_path),
    )
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: {"ETHUSDT": _frame(ts)})
    monkeypatch.setattr(worker, "_entry_qty", lambda mark_price, size_ratio: 1.0)
    monkeypatch.setattr(
        worker,
        "_build_signal_frame",
        lambda *, symbol, frame_15m, route, timeframe: pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "TREND",
                    "entry_signal": True,
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"],
                    "position_size_ratio": 0.1,
                }
            ]
        ),
    )

    summary = worker.run_once()

    route_key = build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")
    assert summary["routes"][route_key]["trade"]["status"] == "risk_blocked"
    assert summary["routes"][route_key]["trade"]["risk"]["risk_blocked"] is True
    assert "RISK_SYMBOL_EXPOSURE" in summary["routes"][route_key]["trade"]["risk"]["block_reason_codes"]
    assert transport.calls == 0


def test_worker_blocks_entry_when_correlation_gate_breaches(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    settings_path = tmp_path / "config.prod.yaml"
    _write_settings(settings_path, max_symbol=8.0, max_portfolio=25.0, max_dd=8.0)
    worker = _worker(
        tmp_path,
        transport,
        execution_mode="production",
        settings_path=str(settings_path),
    )
    worker._risk_manager = worker._risk_manager.__class__(worker._risk_manager.config.__class__(max_correlated_exposure_pct=10.0))
    worker.position_manager.replace_positions(
        [
            PositionState(
                symbol="BTCUSDT",
                side="buy",
                qty=2.0,
                avg_entry=100.0,
                unrealized_pnl_pct=0.0,
                add_count=0,
                updated_at=datetime.now(UTC),
                strategy="legacy",
                timeframe="15m",
            ),
            PositionState(
                symbol="XRPUSDT",
                side="buy",
                qty=2.0,
                avg_entry=100.0,
                unrealized_pnl_pct=0.0,
                add_count=0,
                updated_at=datetime.now(UTC),
                strategy="legacy",
                timeframe="15m",
            ),
        ]
    )
    risk_input_path = tmp_path / "risk" / "risk_input.parquet"
    _write_risk_input(
        risk_input_path,
        [
            {
                "timestamp": datetime.now(UTC),
                "symbol": "ETHUSDT",
                "current_equity": 1000.0,
                "equity_peak": 1000.0,
                "symbol_exposure_pct": 0.0,
                "portfolio_exposure_pct": 40.0,
                "concentration_score": 0.5,
                "correlated_exposure_pct": 40.0,
                "vol_weighted_exposure_pct": 20.0,
                "risk_contribution_pct": 5.0,
                "missing_vol_ratio": 0.0,
            }
        ],
    )
    worker.config = WorkerConfig(**{**worker.config.__dict__, "risk_input_path": str(risk_input_path)})
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(
        worker,
        "_load_closed_market_frames",
        lambda: {"ETHUSDT": _frame(ts), "BTCUSDT": _frame(ts), "XRPUSDT": _frame(ts)},
    )
    monkeypatch.setattr(worker, "_entry_qty", lambda mark_price, size_ratio: 0.1)
    monkeypatch.setattr(
        worker,
        "_build_signal_frame",
        lambda *, symbol, frame_15m, route, timeframe: pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "TREND",
                    "entry_signal": symbol == "ETHUSDT",
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"] if symbol == "ETHUSDT" else [],
                    "position_size_ratio": 0.1,
                }
            ]
        ),
    )

    summary = worker.run_once()

    route_key = build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")
    assert summary["routes"][route_key]["trade"]["status"] == "risk_blocked"
    assert "RISK_CORRELATED_EXPOSURE" in summary["routes"][route_key]["trade"]["risk"]["block_reason_codes"]


def test_worker_blocks_entry_when_volatility_gate_breaches(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    settings_path = tmp_path / "config.prod.yaml"
    _write_settings(settings_path, max_symbol=8.0, max_portfolio=25.0, max_dd=8.0)
    worker = _worker(
        tmp_path,
        transport,
        execution_mode="production",
        settings_path=str(settings_path),
    )
    worker._risk_manager = worker._risk_manager.__class__(worker._risk_manager.config.__class__(max_vol_weighted_exposure_pct=10.0))
    risk_input_path = tmp_path / "risk" / "risk_input.parquet"
    _write_risk_input(
        risk_input_path,
        [
            {
                "timestamp": datetime.now(UTC),
                "symbol": "ETHUSDT",
                "current_equity": 1000.0,
                "equity_peak": 1000.0,
                "symbol_exposure_pct": 1.0,
                "portfolio_exposure_pct": 1.0,
                "concentration_score": 1.0,
                "correlated_exposure_pct": 1.0,
                "vol_weighted_exposure_pct": 20.0,
                "risk_contribution_pct": 5.0,
                "missing_vol_ratio": 0.0,
            }
        ],
    )
    worker.config = WorkerConfig(**{**worker.config.__dict__, "risk_input_path": str(risk_input_path)})
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: {"ETHUSDT": _frame(ts)})
    monkeypatch.setattr(worker, "_entry_qty", lambda mark_price, size_ratio: 0.1)
    monkeypatch.setattr(
        worker,
        "_build_signal_frame",
        lambda *, symbol, frame_15m, route, timeframe: pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "TREND",
                    "entry_signal": True,
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"],
                    "position_size_ratio": 0.1,
                }
            ]
        ),
    )

    summary = worker.run_once()

    route_key = build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")
    assert summary["routes"][route_key]["trade"]["status"] == "risk_blocked"
    assert "RISK_VOL_WEIGHTED_EXPOSURE" in summary["routes"][route_key]["trade"]["risk"]["block_reason_codes"]


def test_worker_blocks_entry_when_risk_contribution_gate_breaches(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    settings_path = tmp_path / "config.prod.yaml"
    _write_settings(settings_path, max_symbol=8.0, max_portfolio=25.0, max_dd=8.0)
    worker = _worker(
        tmp_path,
        transport,
        execution_mode="production",
        settings_path=str(settings_path),
    )
    worker._risk_manager = worker._risk_manager.__class__(
        worker._risk_manager.config.__class__(max_risk_contribution_pct=5.0, max_vol_weighted_exposure_pct=100.0)
    )
    risk_input_path = tmp_path / "risk" / "risk_input.parquet"
    _write_risk_input(
        risk_input_path,
        [
            {
                "timestamp": datetime.now(UTC),
                "symbol": "ETHUSDT",
                "current_equity": 1000.0,
                "equity_peak": 1000.0,
                "symbol_exposure_pct": 1.0,
                "portfolio_exposure_pct": 1.0,
                "concentration_score": 1.0,
                "correlated_exposure_pct": 1.0,
                "vol_weighted_exposure_pct": 1.0,
                "risk_contribution_pct": 50.0,
                "missing_vol_ratio": 0.0,
            }
        ],
    )
    worker.config = WorkerConfig(**{**worker.config.__dict__, "risk_input_path": str(risk_input_path)})
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: {"ETHUSDT": _frame(ts)})
    monkeypatch.setattr(worker, "_entry_qty", lambda mark_price, size_ratio: 0.1)
    monkeypatch.setattr(
        worker,
        "_build_signal_frame",
        lambda *, symbol, frame_15m, route, timeframe: pd.DataFrame(
            [
                {
                    "timestamp": ts,
                    "regime": "TREND",
                    "entry_signal": True,
                    "exit_signal": False,
                    "add_signal": False,
                    "pass_filter": True,
                    "signal_reason_codes": ["ENTRY_OK"],
                    "position_size_ratio": 0.1,
                }
            ]
        ),
    )

    summary = worker.run_once()

    route_key = build_route_key(strategy="trend", symbol="ETHUSDT", timeframe="15m")
    assert summary["routes"][route_key]["trade"]["status"] == "risk_blocked"
    assert summary["routes"][route_key]["trade"]["risk"]["risk_blocked"] is True
    assert "RISK_RISK_CONTRIBUTION" in summary["routes"][route_key]["trade"]["risk"]["block_reason_codes"]
    assert transport.calls == 0
