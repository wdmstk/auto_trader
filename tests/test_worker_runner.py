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


def _worker(tmp_path: Path, transport: DummyTransport) -> LiveTradingWorker:
    runtime_state = tmp_path / "runtime" / "control_state.json"
    positions_dir = tmp_path / "positions"
    worker = LiveTradingWorker(
        config=WorkerConfig(
            symbols=("ETHUSDT", "XRPUSDT"),
            trend_symbols=("ETHUSDT",),
            range_symbols=("XRPUSDT",),
            weekly_revalidation_report_path=str(
                tmp_path / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"
            ),
            trend_order_mode="limit",
            range_order_mode="market",
            runtime_state_path=str(runtime_state),
            gateway_state_path=str(tmp_path / "gateway_state.json"),
            positions_dir=str(positions_dir),
            worker_state_path=str(tmp_path / "worker_state.json"),
            order_events_path=str(tmp_path / "order_events.jsonl"),
            market_limit=10,
            poll_interval_sec=0.01,
            max_iterations=1,
        ),
        transport=transport,
    )
    worker._closed_market_frame = lambda raw_frame, timeframe: raw_frame.copy().assign(
        timeframe=timeframe
    )
    return worker


def _write_weekly_report(path: Path, *, trend: list[str], range_: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "selection": {
                    "trend_enabled_symbols": trend,
                    "range_enabled_symbols": range_,
                    "timeframe": "15m",
                }
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
                }
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
                "selection": {
                    "trade_routes": [
                        {
                            "symbol": "XRPUSDT",
                            "strategy": "range",
                            "timeframe": "15m",
                            "expected_regime": "RANGE",
                            "candidate_status": "core",
                        },
                        {
                            "symbol": "XRPUSDT",
                            "strategy": "trend",
                            "timeframe": "15m",
                            "expected_regime": "TREND",
                            "candidate_status": "core",
                        },
                    ]
                }
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

    def build_signal_frame(
        *, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str
    ) -> pd.DataFrame:
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
    assert (
        worker.position_manager.get(
            build_route_key(strategy="legacy", symbol="ETHUSDT", timeframe="15m")
        ).qty
        == 0.0
    )


def test_worker_refreshes_symbols_from_weekly_report(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    weekly_path = (
        tmp_path / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"
    )
    _write_weekly_report(weekly_path, trend=["ADAUSDT"], range_=["BNBUSDT"])
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    frames = {symbol: _frame(ts) for symbol in ("ETHUSDT", "ADAUSDT", "BNBUSDT")}
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: frames)

    def build_signal_frame(
        *, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str
    ) -> pd.DataFrame:
        is_entry = (symbol == "ADAUSDT" and route == "trend") or (
            symbol == "BNBUSDT" and route == "range"
        )
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
    weekly_path = (
        tmp_path / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"
    )
    _write_weekly_route_report(weekly_path)
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    frames = {symbol: _frame(ts) for symbol in ("ETHUSDT", "XRPUSDT", "BNBUSDT")}
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: frames)

    def build_signal_frame(
        *, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str
    ) -> pd.DataFrame:
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


def test_worker_keeps_previous_symbols_when_weekly_report_is_broken(
    tmp_path: Path, monkeypatch
) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    weekly_path = (
        tmp_path / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"
    )
    _write_weekly_report(weekly_path, trend=["ADAUSDT"], range_=["BNBUSDT"])
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts1 = datetime.now(UTC).replace(microsecond=0)
    frames1 = {symbol: _frame(ts1) for symbol in ("ETHUSDT", "ADAUSDT", "BNBUSDT")}
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: frames1)

    def build_signal_frame(
        *, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str
    ) -> pd.DataFrame:
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

    def build_signal_frame_second(
        *, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str
    ) -> pd.DataFrame:
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
    assert transport.calls == 2


def test_worker_supports_multiple_routes_for_same_symbol(tmp_path: Path, monkeypatch) -> None:
    transport = DummyTransport()
    worker = _worker(tmp_path, transport)
    weekly_path = (
        tmp_path / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"
    )
    _write_weekly_multi_route_report(weekly_path)
    _runtime_state(tmp_path / "runtime" / "control_state.json", trading_enabled=True)
    ts = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(worker, "_load_closed_market_frames", lambda: {"XRPUSDT": _frame(ts)})

    def build_signal_frame(
        *, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str
    ) -> pd.DataFrame:
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
    assert worker.position_manager.get(range_key) is not None
    assert worker.position_manager.get(trend_key) is not None


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

    def build_signal_frame(
        *, symbol: str, frame_15m: pd.DataFrame, route: str, timeframe: str
    ) -> pd.DataFrame:
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
