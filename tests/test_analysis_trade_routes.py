from __future__ import annotations

import pytest

from auto_trader.analysis.trade_routes import (
    build_trade_route_selection,
    resolve_live_trade_routes,
    validate_trade_route_selection,
)


def test_build_trade_route_selection_prefers_core_probe_over_watchlist() -> None:
    report = {
        "statistical_qualification": {
            "status": "pass",
            "qualification_report_path": "qualification.json",
            "passed_route_keys": ["range:BNBUSDT:30m"],
        },
        "candidates": {
            "rows": [
                {
                    "symbol": "BNBUSDT",
                    "timeframe": "15m",
                    "strategy": "range",
                    "candidate_status": "probe",
                    "candidate_score": 10.0,
                    "pf_mean": 1.02,
                    "expectancy_bps_mean": 175.9,
                    "period_pnl_mean": 8.1,
                    "max_dd_mean": 0.002,
                }
            ]
        },
        "range_probe_candidates": {
            "rows": [
                {
                    "symbol": "BNBUSDT",
                    "timeframe": "30m",
                    "strategy": "range",
                    "candidate_status": "core",
                    "candidate_score": 100.0,
                    "pf_mean": 127.8,
                    "expectancy_bps_mean": 290.9,
                    "period_pnl_mean": 38.9,
                    "max_dd_mean": 0.0019,
                }
            ]
        },
    }

    out = build_trade_route_selection(report, default_timeframe="15m")

    assert out["trend_enabled_symbols"] == []
    assert out["range_enabled_symbols"] == ["BNBUSDT"]
    assert out["symbol_timeframes"] == {"BNBUSDT": "30m"}
    assert out["trade_routes"][0]["strategy"] == "range"
    assert out["trade_routes"][0]["timeframe"] == "30m"
    assert out["trade_routes"][0]["expected_regime"] == "RANGE"
    assert out["trade_routes"][0]["statistical_status"] == "pass"


def test_build_trade_route_selection_is_fail_closed_without_statistical_report() -> None:
    report = {
        "candidates": {
            "rows": [
                {
                    "symbol": "ETHUSDT",
                    "timeframe": "15m",
                    "strategy": "trend",
                    "candidate_status": "core",
                }
            ]
        }
    }
    assert build_trade_route_selection(report)["trade_routes"] == []


def test_validate_trade_route_selection_rejects_missing_statistical_status() -> None:
    selection = {
        "timeframe": "15m",
        "trade_routes": [
            {
                "symbol": "ETHUSDT",
                "strategy": "trend",
                "timeframe": "15m",
                "expected_regime": "TREND",
                "candidate_status": "core",
            }
        ],
    }

    with pytest.raises(ValueError, match="statistical_status is required"):
        validate_trade_route_selection(selection)


def test_resolve_live_trade_routes_prefers_selection_trade_routes() -> None:
    report = {
        "selection": {
            "timeframe": "15m",
            "trade_routes": [
                {
                    "symbol": "ETHUSDT",
                    "strategy": "trend",
                    "timeframe": "1h",
                    "expected_regime": "TREND",
                    "candidate_status": "core",
                    "selection_source": "autotune",
                    "selected_stage": "trend_next_step",
                    "config_label": "cooldown0_exit0.08",
                    "params": {
                        "trend_reentry_cooldown_bars": 0,
                        "trend_efficiency_exit_threshold": 0.08,
                    },
                },
                {
                    "symbol": "XRPUSDT",
                    "strategy": "range",
                    "timeframe": "30m",
                    "expected_regime": "RANGE",
                    "candidate_status": "core",
                },
            ],
        }
    }

    out = resolve_live_trade_routes(report, default_timeframe="15m")

    assert out["source"] == "selection.trade_routes"
    assert out["trend_enabled_symbols"] == ["ETHUSDT"]
    assert out["range_enabled_symbols"] == ["XRPUSDT"]
    assert out["symbol_timeframes"] == {"ETHUSDT": "1h", "XRPUSDT": "30m"}
    assert out["trade_routes"][0]["strategy"] == "trend"
    assert out["trade_routes"][1]["strategy"] == "range"
    assert out["trade_routes"][0]["selection_source"] == "autotune"
    assert out["trade_routes"][0]["selected_stage"] == "trend_next_step"
    assert out["trade_routes"][0]["config_label"] == "cooldown0_exit0.08"
    assert out["trade_routes"][0]["params"]["trend_efficiency_exit_threshold"] == 0.08


def test_resolve_live_trade_routes_keeps_multiple_routes_per_symbol() -> None:
    report = {
        "selection": {
            "timeframe": "15m",
            "trade_routes": [
                {
                    "symbol": "XRPUSDT",
                    "strategy": "trend",
                    "timeframe": "15m",
                    "expected_regime": "TREND",
                    "candidate_status": "core",
                },
                {
                    "symbol": "XRPUSDT",
                    "strategy": "range",
                    "timeframe": "15m",
                    "expected_regime": "RANGE",
                    "candidate_status": "core",
                },
            ],
        }
    }

    out = resolve_live_trade_routes(report, default_timeframe="15m")

    assert len(out["trade_routes"]) == 2
    assert [route["strategy"] for route in out["trade_routes"]] == ["trend", "range"]


def test_resolve_live_trade_routes_falls_back_to_enabled_symbols() -> None:
    report = {
        "selection": {
            "timeframe": "15m",
            "trend_enabled_symbols": ["ETHUSDT", "XRPUSDT"],
            "range_enabled_symbols": ["XRPUSDT", "SOLUSDT"],
        }
    }

    out = resolve_live_trade_routes(report, default_timeframe="15m")

    assert out["source"] == "selection.enabled_symbols"
    assert out["trend_enabled_symbols"] == ["ETHUSDT", "XRPUSDT"]
    assert out["range_enabled_symbols"] == ["SOLUSDT"]
    assert out["symbol_timeframes"] == {"ETHUSDT": "15m", "XRPUSDT": "15m", "SOLUSDT": "15m"}
    assert [route["symbol"] for route in out["trade_routes"]] == [
        "ETHUSDT",
        "XRPUSDT",
        "SOLUSDT",
    ]


def test_build_trade_route_selection_preserves_seed_manifest_params() -> None:
    report = {
        "statistical_qualification": {
            "status": "pass",
            "qualification_report_path": "qualification.json",
            "passed_route_keys": ["trend:BNBUSDT:1h"],
        },
        "candidates": {
            "rows": [
                {
                    "symbol": "BNBUSDT",
                    "timeframe": "1h",
                    "strategy": "trend",
                    "candidate_status": "core",
                    "candidate_score": 50.0,
                    "pf_mean": 1.34,
                    "expectancy_bps_mean": 18.23,
                    "period_pnl_mean": 7.85,
                    "max_dd_mean": 0.003,
                    "closed_trades_mean": 10.75,
                    "statistical_status": "pass",
                }
            ]
        },
    }
    seed_manifest = {
        "selection": {
            "trade_routes": [
                {
                    "symbol": "BNBUSDT",
                    "strategy": "trend",
                    "timeframe": "1h",
                    "expected_regime": "TREND",
                    "candidate_status": "core",
                    "selection_source": "autotune",
                    "selected_stage": "trend_next_step",
                    "config_label": "cooldown0_exit0.02",
                    "params": {
                        "trend_reentry_cooldown_bars": 0,
                        "trend_efficiency_exit_threshold": 0.02,
                    },
                }
            ]
        }
    }

    out = build_trade_route_selection(report, default_timeframe="15m", seed_manifest=seed_manifest)

    assert out["trade_routes"][0]["selected_stage"] == "trend_next_step"
    assert out["trade_routes"][0]["selection_source"] == "autotune"
    assert out["trade_routes"][0]["params"]["trend_reentry_cooldown_bars"] == 0
    assert out["trade_routes"][0]["statistical_status"] == "pass"


def test_build_trade_route_selection_keeps_seed_core_route_when_statistical_fails() -> None:
    report = {
        "statistical_qualification": {
            "status": "fail",
            "qualification_report_path": "qualification.json",
            "passed_route_keys": [],
        },
        "candidates": {
            "rows": [
                {
                    "symbol": "BNBUSDT",
                    "timeframe": "1h",
                    "strategy": "trend",
                    "candidate_status": "core",
                    "candidate_score": 50.0,
                    "pf_mean": 1.21,
                    "expectancy_bps_mean": 7.43,
                    "period_pnl_mean": 0.82,
                    "max_dd_mean": 0.0036,
                    "closed_trades_mean": 11.75,
                }
            ]
        },
    }
    seed_manifest = {
        "selection": {
            "trade_routes": [
                {
                    "symbol": "BNBUSDT",
                    "strategy": "trend",
                    "timeframe": "1h",
                    "expected_regime": "TREND",
                    "candidate_status": "core",
                    "selection_source": "autotune",
                    "selected_stage": "trend_next_step",
                }
            ]
        }
    }

    out = build_trade_route_selection(
        report,
        default_timeframe="15m",
        seed_manifest=seed_manifest,
        statistical_gate_mode="soft",
    )

    assert len(out["trade_routes"]) == 1
    assert out["trade_routes"][0]["symbol"] == "BNBUSDT"
    assert out["trade_routes"][0]["statistical_status"] == "fail"


def test_build_trade_route_selection_drops_seed_core_route_in_hard_mode() -> None:
    report = {
        "statistical_qualification": {
            "status": "fail",
            "qualification_report_path": "qualification.json",
            "passed_route_keys": [],
        },
        "candidates": {
            "rows": [
                {
                    "symbol": "BNBUSDT",
                    "timeframe": "1h",
                    "strategy": "trend",
                    "candidate_status": "core",
                }
            ]
        },
    }
    seed_manifest = {
        "selection": {
            "trade_routes": [
                {
                    "symbol": "BNBUSDT",
                    "strategy": "trend",
                    "timeframe": "1h",
                    "expected_regime": "TREND",
                    "candidate_status": "core",
                }
            ]
        }
    }

    out = build_trade_route_selection(
        report,
        default_timeframe="15m",
        seed_manifest=seed_manifest,
        statistical_gate_mode="hard",
    )

    assert out["trade_routes"] == []
    assert out["dropped_routes"][0]["symbol"] == "BNBUSDT"
    assert out["dropped_routes"][0]["dropped_reason"] == "statistical_fail"


def test_build_trade_route_selection_drops_failing_seed_route_in_production_style_report() -> None:
    report = {
        "statistical_qualification": {
            "status": "fail",
            "qualification_report_path": "qualification.json",
            "passed_route_keys": [],
        },
        "selection": {
            "timeframe": "15m",
            "trade_routes": [
                {
                    "symbol": "SOLUSDT",
                    "strategy": "trend",
                    "timeframe": "15m",
                    "expected_regime": "TREND",
                    "candidate_status": "core",
                    "statistical_status": "fail",
                    "selection_source": "autotune",
                }
            ],
        },
    }

    out = build_trade_route_selection(
        report,
        default_timeframe="15m",
        seed_manifest=report,
        statistical_gate_mode="hard",
    )

    assert out["trade_routes"] == []
    assert out["dropped_routes"][0]["symbol"] == "SOLUSDT"
    assert out["dropped_routes"][0]["dropped_reason"] == "statistical_fail"
