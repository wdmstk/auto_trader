from __future__ import annotations

from auto_trader.analysis.trade_routes import (
    build_trade_route_selection,
    resolve_live_trade_routes,
)


def test_build_trade_route_selection_prefers_core_probe_over_watchlist() -> None:
    report = {
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
