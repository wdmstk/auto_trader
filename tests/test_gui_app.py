# Dynamic Streamlit payloads are asserted as nested JSON-like objects.
# mypy: disable-error-code="attr-defined,no-untyped-def,index,operator"

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import auto_trader.gui.app as gui_app
from auto_trader.gui.app import (
    _candidate_frame,
    _candidate_trade_routes_frame,
    _load_candidate_report,
    _load_weekly_candidate_report,
    _manifest_weekly_diff_rows,
    _operator_summary,
    _route_selection_path,
    _weekly_revalidation_report_path,
    _worker_trade_routes_frame,
)
from auto_trader.worker.state import WorkerState


def test_load_candidate_report_merges_weekly_range_probe(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate_report.json"
    weekly_path = tmp_path / "weekly_revalidation_report.json"

    candidate_path.write_text(
        json.dumps({"rows": [{"symbol": "XRPUSDT", "candidate_status": "core"}]}),
        encoding="utf-8",
    )
    weekly_path.write_text(
        json.dumps(
            {
                "range_probe_candidates": {
                    "timeframe_reports": [
                        {
                            "timeframe": "30m",
                            "core_symbols": ["BNBUSDT"],
                            "probe_symbols": [],
                            "watchlist_symbols": [],
                            "rows": [
                                {
                                    "symbol": "BNBUSDT",
                                    "strategy": "range",
                                    "candidate_status": "core",
                                    "pf_mean": 1.8,
                                    "expectancy_bps_mean": 24.0,
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    out = _load_candidate_report(candidate_path, weekly_path)

    assert any(row.get("symbol") == "XRPUSDT" for row in out["rows"] if isinstance(row, dict))
    assert any(row.get("symbol") == "BNBUSDT" and row.get("timeframe") == "30m" for row in out["rows"] if isinstance(row, dict))
    assert out["range_probe_candidates"]["timeframe_reports"][0]["timeframe"] == "30m"
    assert out["range_probe_candidates"]["timeframe_reports"][0]["core_symbols"] == ["BNBUSDT"]


def test_load_weekly_candidate_report_uses_weekly_candidates(tmp_path: Path) -> None:
    weekly_path = tmp_path / "weekly_revalidation_report.json"

    weekly_path.write_text(
        json.dumps(
            {
                "candidates": {
                    "rows": [
                        {
                            "symbol": "ETHUSDT",
                            "strategy": "trend",
                            "candidate_status": "core",
                            "pf_mean": 2.1,
                        }
                    ]
                },
                "range_probe_candidates": {
                    "rows": [
                        {
                            "symbol": "BNBUSDT",
                            "strategy": "range",
                            "candidate_status": "probe",
                            "pf_mean": 1.4,
                        }
                    ]
                },
                "decision": {
                    "status": "warn",
                    "market_reason": {"reason": "market criteria satisfied"},
                },
            }
        ),
        encoding="utf-8",
    )

    out = _load_weekly_candidate_report(weekly_path)

    assert any(row.get("symbol") == "ETHUSDT" for row in out["rows"] if isinstance(row, dict))
    assert any(row.get("symbol") == "BNBUSDT" and row.get("candidate_status") == "probe" for row in out["rows"] if isinstance(row, dict))
    assert "range_probe_candidates" in out
    assert out["decision"]["status"] == "warn"


def test_manifest_weekly_diff_rows_from_weekly_report() -> None:
    rows = _manifest_weekly_diff_rows(
        {
            "manifest_weekly_diff": {
                "route_count": 1,
                "rows": [
                    {
                        "route_key": "trend:BNBUSDT:1h",
                        "selected_stage": "trend_next_step",
                        "metric_match": True,
                        "weekly_statistical_status": "fail",
                        "source_trade_oos_days": 25.04,
                        "weekly_trade_oos_days": 25.04,
                        "weekly_fold_oos_days": 47.38,
                        "fold_window_drift_days": 22.34,
                        "closed_trades_mean": 8.25,
                        "statistical_reasons": ["min_oos_days", "min_route_trades"],
                    }
                ],
            }
        }
    )

    assert len(rows) == 1
    assert rows[0]["route"] == "trend:BNBUSDT:1h"
    assert rows[0]["metrics_match"] == "yes"
    assert rows[0]["weekly_fold_oos_days"] == 47.38
    assert rows[0]["statistical_reasons"] == "min_oos_days, min_route_trades"


def test_load_candidate_report_uses_route_selection_manifest_when_rows_missing(
    tmp_path: Path,
) -> None:
    route_path = tmp_path / "autotune_full_route_manifest.json"
    route_path.write_text(
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
                            "pf_mean": 1.26,
                            "expectancy_bps_mean": 4.9,
                            "period_pnl_mean": 2.34,
                            "max_dd_mean": 0.001,
                            "closed_trades_mean": 36.0,
                            "statistical_status": "pass",
                            "selection_source": "autotune",
                            "selected_stage": "hold",
                            "config_label": "range_hold16",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    out = _load_candidate_report(
        tmp_path / "candidate_report.json",
        tmp_path / "weekly_revalidation_report.json",
        route_path,
    )

    frame = _candidate_frame(out)
    assert not frame.empty
    assert frame.iloc[0]["symbol"] == "SOLUSDT"
    assert frame.iloc[0]["strategy"] == "range"
    assert frame.iloc[0]["candidate_status"] == "core"
    assert float(frame.iloc[0]["pf_mean"]) == 1.26
    assert out["core_symbols"] == ["SOLUSDT"]


def test_load_weekly_candidate_report_falls_back_to_route_selection_manifest(
    tmp_path: Path,
) -> None:
    route_path = tmp_path / "autotune_full_route_manifest.json"
    route_path.write_text(
        json.dumps(
            {
                "source": "autotune_full_manifest",
                "selection": {
                    "trade_routes": [
                        {
                            "symbol": "ETHUSDT",
                            "strategy": "trend",
                            "timeframe": "1h",
                            "expected_regime": "TREND",
                            "candidate_status": "core",
                            "pf_mean": 2.48,
                            "expectancy_bps_mean": 11.8,
                            "period_pnl_mean": 1.0,
                            "max_dd_mean": 0.011,
                            "closed_trades_mean": 10.75,
                            "statistical_status": "pass",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    out = _load_weekly_candidate_report(
        tmp_path / "missing_weekly_revalidation_report.json",
        route_path,
    )

    frame = _candidate_frame(out)
    assert not frame.empty
    assert frame.iloc[0]["symbol"] == "ETHUSDT"
    assert float(frame.iloc[0]["expectancy_bps_mean"]) == 11.8
    assert out["core_symbols"] == ["ETHUSDT"]


def test_weekly_revalidation_report_path_prefers_runtime_env(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    env_dir = data_dir / "validation" / "weekly_autotune"
    env_dir.mkdir(parents=True)
    weekly_path = data_dir / "validation" / "weekly_autotune" / "weekly_revalidation" / "weekly_revalidation_report.json"
    env_path = env_dir / "route_selection_runtime.env"
    env_path.write_text(
        f"WEEKLY_REVALIDATION_REPORT_PATH={weekly_path}\n" f"ROUTE_SELECTION_PATH={weekly_path}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gui_app, "DATA_DIR", data_dir)

    assert _weekly_revalidation_report_path() == weekly_path
    assert _route_selection_path() == weekly_path


def test_load_weekly_candidate_report_uses_runtime_env_default_path(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    env_dir = data_dir / "validation" / "weekly_autotune"
    weekly_dir = env_dir / "weekly_revalidation"
    env_dir.mkdir(parents=True)
    weekly_dir.mkdir(parents=True)
    weekly_path = weekly_dir / "weekly_revalidation_report.json"
    (env_dir / "route_selection_runtime.env").write_text(
        f"WEEKLY_REVALIDATION_REPORT_PATH={weekly_path}\n",
        encoding="utf-8",
    )
    weekly_path.write_text(
        json.dumps(
            {
                "candidates": {
                    "rows": [
                        {
                            "symbol": "SOLUSDT",
                            "strategy": "range",
                            "candidate_status": "core",
                            "pf_mean": 1.26,
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(gui_app, "DATA_DIR", data_dir)

    out = _load_weekly_candidate_report()

    assert any(row.get("symbol") == "SOLUSDT" for row in out["rows"] if isinstance(row, dict))


def test_operator_summary_prefers_weekly_decision_reasons() -> None:
    worker_state = WorkerState(updated_at="2099-06-07T00:00:00Z")
    candidate_report = {
        "status": "warn",
        "core_symbols": ["ETHUSDT", "XRPUSDT"],
        "probe_symbols": ["ADAUSDT"],
        "watchlist_symbols": ["BTCUSDT"],
        "candidate_counts": {"core": 2, "probe": 1, "watchlist": 1},
        "limit_metrics": {
            "limit_fill_rate_mean": 0.35,
            "limit_taker_like_rate_mean": 0.62,
        },
        "decision": {
            "status": "warn",
            "market_reason": {"reason": "market criteria satisfied"},
            "limit_reason": {"reason": "limit failed: trend_pf_ge_1_2"},
            "drift_reason": {"reason": "drift criteria satisfied"},
        },
    }

    summary = _operator_summary(
        runtime_state={"trading_enabled": True, "emergency_stop": False},
        worker_state=worker_state,
        latest_metrics={"timestamp": "2099-06-07T00:00:00Z"},
        risk_df=pd.DataFrame(),
        risk_input_df=pd.DataFrame(),
        candidate_report=candidate_report,
    )

    assert summary["decision_status"] == "warn"
    assert summary["focus"] == "core routes=2 probe routes=1 watchlist routes=1"
    assert summary["limit_fill_rate"] == 0.35
    assert summary["limit_taker_like_rate"] == 0.62
    assert "market criteria satisfied" in summary["reasons"]
    assert summary["next_action"] == "Review weekly market/limit reasons and adjust symbol gating."


def test_worker_trade_routes_frame_uses_route_metadata() -> None:
    worker_state = WorkerState(
        last_results={
            "range:BNBUSDT:30m": {
                "status": "ok",
                "risk_blocked": False,
                "route": {
                    "symbol": "BNBUSDT",
                    "strategy": "range",
                    "timeframe": "30m",
                    "expected_regime": "RANGE",
                    "candidate_status": "core",
                    "statistical_status": "fail",
                    "route_policy": "test-only / statistical-fail",
                },
                "signal": {
                    "regime": "RANGE",
                    "timeframe": "30m",
                    "entry_signal": True,
                    "exit_signal": False,
                },
                "trade": {"status": "entry"},
            }
        }
    )

    frame = _worker_trade_routes_frame(worker_state)

    assert not frame.empty
    assert frame.iloc[0]["symbol"] == "BNBUSDT"
    assert frame.iloc[0]["strategy"] == "range"
    assert frame.iloc[0]["timeframe"] == "30m"
    assert frame.iloc[0]["expected_regime"] == "RANGE"
    assert frame.iloc[0]["statistical_status"] == "fail"
    assert frame.iloc[0]["route_policy"] == "test-only / statistical-fail"
    assert bool(frame.iloc[0]["entry_signal"]) is True


def test_candidate_trade_routes_frame_uses_weekly_selection_routes() -> None:
    candidate_report = {
        "selection": {
            "trade_routes": [
                {
                    "symbol": "BNBUSDT",
                    "strategy": "range",
                    "timeframe": "30m",
                    "expected_regime": "RANGE",
                    "candidate_status": "core",
                    "statistical_status": "fail",
                    "route_policy": "test-only / statistical-fail",
                }
            ]
        }
    }

    frame = _candidate_trade_routes_frame(candidate_report)

    assert not frame.empty
    assert frame.iloc[0]["symbol"] == "BNBUSDT"
    assert frame.iloc[0]["strategy"] == "range"
    assert frame.iloc[0]["timeframe"] == "30m"
    assert frame.iloc[0]["statistical_status"] == "fail"
    assert frame.iloc[0]["route_policy"] == "test-only / statistical-fail"
    assert frame.iloc[0]["status"] == "configured"


def test_active_worker_symbols_normalizes_route_keys() -> None:
    worker_state = WorkerState(
        last_results={
            "trend:ETHUSDT:15m": {
                "route": {"symbol": "ETHUSDT", "strategy": "trend", "timeframe": "15m"},
            },
            "range:BNBUSDT:30m": {
                "route": {"symbol": "BNBUSDT", "strategy": "range", "timeframe": "30m"},
            },
            "XRPUSDT": {},
        },
        last_processed_bars={
            "trend:ADAUSDT:15m": "2026-06-07T00:00:00Z",
        },
    )

    assert gui_app._active_worker_symbols(worker_state) == [
        "ADAUSDT",
        "BNBUSDT",
        "ETHUSDT",
        "XRPUSDT",
    ]


def test_optional_read_falls_back_when_cache_breaks(tmp_path: Path, monkeypatch) -> None:
    parquet_path = tmp_path / "sample.parquet"
    pd.DataFrame([{"symbol": "BNBUSDT", "value": 1}]).to_parquet(parquet_path, index=False)

    monkeypatch.setattr(
        gui_app,
        "_read_optional_cached",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyError("cache")),
    )

    frame = gui_app._read_optional(parquet_path)

    assert not frame.empty
    assert frame.iloc[0]["symbol"] == "BNBUSDT"


def test_discover_available_symbols_reads_multiple_sources(tmp_path: Path) -> None:
    (tmp_path / "parquet").mkdir()
    (tmp_path / "signals").mkdir()
    (tmp_path / "regime").mkdir()

    pd.DataFrame([{"timestamp": "2026-01-01T00:00:00Z"}]).to_parquet(tmp_path / "parquet" / "BTCUSDT_1m.parquet", index=False)
    pd.DataFrame([{"timestamp": "2026-01-01T00:00:00Z"}]).to_parquet(tmp_path / "signals" / "ETHUSDT_15m_trend_signals.parquet", index=False)
    pd.DataFrame([{"timestamp": "2026-01-01T00:00:00Z"}]).to_parquet(tmp_path / "regime" / "XRPUSDT_30m_regime.parquet", index=False)

    symbols = gui_app._discover_available_symbols(tmp_path)

    assert symbols == ["BTCUSDT", "ETHUSDT", "XRPUSDT"]


def test_discover_symbol_timeframes_prioritizes_1m(tmp_path: Path) -> None:
    (tmp_path / "parquet").mkdir()
    (tmp_path / "signals").mkdir()
    pd.DataFrame([{"timestamp": "2026-01-01T00:00:00Z"}]).to_parquet(tmp_path / "parquet" / "BTCUSDT_30m.parquet", index=False)
    pd.DataFrame([{"timestamp": "2026-01-01T00:00:00Z"}]).to_parquet(tmp_path / "parquet" / "BTCUSDT_1m.parquet", index=False)
    pd.DataFrame([{"timestamp": "2026-01-01T00:00:00Z"}]).to_parquet(tmp_path / "signals" / "BTCUSDT_5m_trend_signals.parquet", index=False)

    timeframes = gui_app._discover_symbol_timeframes("BTCUSDT", tmp_path)

    assert timeframes[0] == "1m"
    assert set(timeframes) >= {"1m", "5m", "30m"}


def test_discover_backtest_runs_reads_metadata(tmp_path: Path) -> None:
    backtest_dir = tmp_path / "backtest" / "ETHUSDT_1m_trend_20260606"
    backtest_dir.mkdir(parents=True)
    pd.DataFrame([{"timestamp": "2026-01-01T00:00:00Z", "equity": 100.0}]).to_parquet(backtest_dir / "portfolio.parquet", index=False)
    (backtest_dir / "metadata.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-06-06T00:00:00Z",
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "strategy": "trend",
                "output_dir": str(backtest_dir),
            }
        ),
        encoding="utf-8",
    )

    runs = gui_app._discover_backtest_runs(tmp_path)

    assert len(runs) == 1
    assert runs[0]["symbol"] == "ETHUSDT"
    assert runs[0]["timeframe"] == "1m"
    assert runs[0]["strategy"] == "trend"


def test_inject_ui_stability_styles_adds_reload_css(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_markdown(*args: object, **kwargs: object) -> None:
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(gui_app.st, "markdown", fake_markdown)

    gui_app._inject_ui_stability_styles()

    assert captured["kwargs"]["unsafe_allow_html"] is True
    css = str(captured["args"][0])
    assert '[data-testid="stAppViewContainer"]' in css
    assert "opacity: 1 !important;" in css


def test_resolve_futures_testnet_credentials_loads_repo_env(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "BINANCE_FUTURES_TESTNET_API_KEY=from_env_file\n" "BINANCE_FUTURES_TESTNET_API_SECRET=from_env_secret\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gui_app, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gui_app, "_GUI_ENV_LOADED", False)
    monkeypatch.delenv("BINANCE_FUTURES_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_FUTURES_TESTNET_API_SECRET", raising=False)

    key, secret = gui_app._resolve_futures_testnet_credentials()

    assert key == "from_env_file"
    assert secret == "from_env_secret"


def test_core_symbol_focus_rows_uses_core_candidates_only() -> None:
    candidate_report = {
        "core_symbols": ["AAAUSDT", "BBBUSDT"],
        "best_by_symbol_strategy": [
            {
                "symbol": "AAAUSDT",
                "timeframe": "30m",
                "strategy": "range",
                "candidate_status": "watchlist",
                "candidate_score": 10.0,
            },
            {
                "symbol": "AAAUSDT",
                "timeframe": "15m",
                "strategy": "trend",
                "candidate_status": "core",
                "candidate_score": 30.0,
            },
            {
                "symbol": "BBBUSDT",
                "timeframe": "1h",
                "strategy": "trend",
                "candidate_status": "core",
                "candidate_score": 20.0,
            },
            {
                "symbol": "CCCUSDT",
                "timeframe": "1m",
                "strategy": "trend",
                "candidate_status": "core",
                "candidate_score": 99.0,
            },
        ],
    }

    rows = gui_app._core_symbol_focus_rows(candidate_report)

    assert [row["symbol"] for row in rows] == ["AAAUSDT", "BBBUSDT"]
    assert rows[0]["timeframe"] == "15m"
    assert rows[0]["strategy"] == "trend"
    assert rows[1]["timeframe"] == "1h"


def test_position_reconciliation_frame_compares_net_exchange_positions() -> None:
    local = pd.DataFrame(
        [
            {
                "symbol": "SOLUSDT",
                "strategy": "trend",
                "timeframe": "15m",
                "route_key": "trend:SOLUSDT:15m",
                "side": "buy",
                "qty": 1.45,
            }
        ]
    )
    exchange = pd.DataFrame(
        [
            {
                "symbol": "BTCUSDT",
                "position_side": "BOTH",
                "side": "buy",
                "position_amt": 0.001,
                "qty": 0.001,
                "entry_price": 64207.2,
                "mark_price": 64540.0,
                "unrealized_profit": 0.3328,
                "leverage": 3,
                "margin_type": "CROSS",
                "update_time": 1781424000162,
                "update_at": "2026-06-14T08:00:00.162000+00:00",
            }
        ]
    )

    out = gui_app._position_reconciliation_frame(local, exchange)

    assert list(out["symbol"]) == ["BTCUSDT", "SOLUSDT"]
    btc = out[out["symbol"] == "BTCUSDT"].iloc[0]
    sol = out[out["symbol"] == "SOLUSDT"].iloc[0]
    assert btc["status"] == "exchange_only"
    assert float(btc["qty_diff"]) == -0.001
    assert sol["status"] == "local_only"
    assert float(sol["qty_diff"]) == 1.45


def test_downsample_for_chart_preserves_signal_rows() -> None:
    frame = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-01-01T00:00:00Z"),
                "entry_signal": False,
                "exit_signal": False,
                "risk_blocked": False,
            }
            for _ in range(50)
        ]
    )
    frame.loc[10, "entry_signal"] = True
    frame.loc[20, "exit_signal"] = True
    frame.loc[30, "risk_blocked"] = True

    out = gui_app._downsample_for_chart(frame, max_points=10)

    assert bool(out["entry_signal"].any()) is True
    assert bool(out["exit_signal"].any()) is True
    assert bool(out["risk_blocked"].any()) is True
