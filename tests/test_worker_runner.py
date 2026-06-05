from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from auto_trader.position.models import PositionState
from auto_trader.worker.runner import LiveTradingWorker, WorkerConfig


class DummyTransport:
    def __init__(self) -> None:
        self.calls = 0

    def send_order(self, order):
        self.calls += 1
        return True, f"ord_{self.calls:06d}", "accepted"


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
    return LiveTradingWorker(
        config=WorkerConfig(
            symbols=("ETHUSDT", "XRPUSDT"),
            trend_symbols=("ETHUSDT",),
            range_symbols=("XRPUSDT",),
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
        lambda *, symbol, frame_15m, route: pd.DataFrame(
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

    def build_signal_frame(*, symbol: str, frame_15m: pd.DataFrame, route: str) -> pd.DataFrame:
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
    assert first["symbols"]["ETHUSDT"]["trade"]["gateway_status"] == "ack"
    assert second["symbols"]["ETHUSDT"]["status"] == "already_processed"
    state = json.loads((tmp_path / "worker_state.json").read_text(encoding="utf-8"))
    assert state["last_processed_bars"]["trend:ETHUSDT"] == str(pd.to_datetime(ts, utc=True))


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
    assert worker.position_manager.get("ETHUSDT").qty == 0.0
