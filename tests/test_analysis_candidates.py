from __future__ import annotations

from pathlib import Path

from auto_trader.analysis.candidates import (
    CandidateThresholds,
    recommend_symbol_candidates,
    write_candidate_report,
)


def test_recommend_symbol_candidates_classifies_rows(tmp_path: Path) -> None:
    summary = {
        "rows": [
            {
                "symbol": "ETHUSDT",
                "timeframe": "15m",
                "strategy": "trend",
                "pf_mean": 2.2,
                "expectancy_bps_mean": 13.5,
                "period_pnl_mean": 4.5,
                "max_dd_mean": 0.02,
                "closed_trades_mean": 3.0,
            },
            {
                "symbol": "BTCUSDT",
                "timeframe": "30m",
                "strategy": "trend",
                "pf_mean": 0.95,
                "expectancy_bps_mean": 3.0,
                "period_pnl_mean": 1.0,
                "max_dd_mean": 0.05,
                "closed_trades_mean": 2.0,
            },
            {
                "symbol": "SOLUSDT",
                "timeframe": "1h",
                "strategy": "range",
                "pf_mean": 0.5,
                "expectancy_bps_mean": -1.0,
                "period_pnl_mean": -0.5,
                "max_dd_mean": 0.2,
                "closed_trades_mean": 2.0,
            },
        ]
    }

    out = recommend_symbol_candidates(summary, thresholds=CandidateThresholds())
    assert out["core_symbols"] == ["ETHUSDT"]
    assert out["probe_symbols"] == ["BTCUSDT"]
    assert out["watchlist_symbols"] == ["SOLUSDT"]
    assert out["timeframes"] == ["15m", "30m", "1h"]
    assert out["best_by_symbol_strategy"][0]["symbol"] == "ETHUSDT"
    assert "limit_metrics" in out
    assert "candidate_counts" in out
    assert out["candidate_counts"]["core"] == 1
    assert out["route_counts"]["core"] == 1
    assert out["symbol_counts"]["core"] == 1

    json_path = tmp_path / "candidate_report.json"
    saved = write_candidate_report(summary, json_path=json_path)
    assert json_path.exists()
    assert saved["status"] == "pass"
    assert "limit_metrics" in saved


def test_recommend_symbol_candidates_exposes_timeframe_reports() -> None:
    summary = {
        "rows": [
            {
                "symbol": "BNBUSDT",
                "timeframe": "15m",
                "strategy": "range",
                "pf_mean": 1.05,
                "expectancy_bps_mean": 12.0,
                "period_pnl_mean": 0.6,
                "max_dd_mean": 0.1,
                "closed_trades_mean": 2.0,
            },
            {
                "symbol": "BNBUSDT",
                "timeframe": "30m",
                "strategy": "range",
                "pf_mean": 1.8,
                "expectancy_bps_mean": 24.0,
                "period_pnl_mean": 1.2,
                "max_dd_mean": 0.03,
                "closed_trades_mean": 2.0,
            },
        ]
    }

    out = recommend_symbol_candidates(summary, thresholds=CandidateThresholds())
    assert out["core_symbols"] == ["BNBUSDT"]
    assert out["timeframes"] == ["15m", "30m"]
    assert [report["timeframe"] for report in out["timeframe_reports"]] == ["15m", "30m"]
    assert out["timeframe_reports"][0]["probe_symbols"] == ["BNBUSDT"]
    assert out["timeframe_reports"][1]["core_symbols"] == ["BNBUSDT"]
    assert "limit_metrics" in out["timeframe_reports"][0]


def test_recommend_symbol_candidates_exposes_shadow_routes() -> None:
    summary = {
        "rows": [
            {
                "symbol": "SOLUSDT",
                "timeframe": "15m",
                "strategy": "range",
                "pf_mean": 1.8,
                "expectancy_bps_mean": 24.0,
                "period_pnl_mean": 1.2,
                "max_dd_mean": 0.03,
                "closed_trades_mean": 2.0,
            },
            {
                "symbol": "SOLUSDT",
                "timeframe": "15m",
                "strategy": "trend",
                "pf_mean": 0.7,
                "expectancy_bps_mean": -2.0,
                "period_pnl_mean": -0.2,
                "max_dd_mean": 0.09,
                "closed_trades_mean": 1.0,
            },
        ]
    }

    out = recommend_symbol_candidates(summary, thresholds=CandidateThresholds())

    assert out["route_counts"] == {"core": 1, "probe": 0, "watchlist": 1}
    assert out["symbol_counts"] == {"core": 1, "probe": 0, "watchlist": 0}
    assert out["shadow_routes_by_symbol"]["SOLUSDT"][0]["strategy"] == "trend"


def test_recommend_symbol_candidates_respects_custom_thresholds() -> None:
    summary = {
        "rows": [
            {
                "symbol": "ETHUSDT",
                "timeframe": "15m",
                "strategy": "trend",
                "pf_mean": 1.12,
                "expectancy_bps_mean": 1.5,
                "period_pnl_mean": 0.2,
                "max_dd_mean": 0.01,
                "closed_trades_mean": 12.0,
            }
        ]
    }

    default_out = recommend_symbol_candidates(summary, thresholds=CandidateThresholds())
    custom_out = recommend_symbol_candidates(
        summary,
        thresholds=CandidateThresholds(core_min_pf=1.1),
    )

    assert default_out["rows"][0]["candidate_status"] == "probe"
    assert custom_out["rows"][0]["candidate_status"] == "core"
