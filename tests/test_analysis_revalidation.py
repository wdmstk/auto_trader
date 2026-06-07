from __future__ import annotations

from pathlib import Path

from auto_trader.analysis.revalidation import build_weekly_revalidation_report


def test_weekly_revalidation_uses_selected_symbols_for_range(tmp_path: Path) -> None:
    market_summary = {
        "rows": [
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "strategy": "range",
                "pf_mean": 0.0,
                "expectancy_bps_mean": 0.0,
                "period_pnl_mean": 0.0,
                "max_dd_mean": 0.0,
            },
            {
                "symbol": "SOLUSDT",
                "timeframe": "15m",
                "strategy": "range",
                "pf_mean": 6.5,
                "expectancy_bps_mean": 37.5,
                "period_pnl_mean": 1.04,
                "max_dd_mean": 0.00054,
            },
            {
                "symbol": "XRPUSDT",
                "timeframe": "15m",
                "strategy": "range",
                "pf_mean": 4.5,
                "expectancy_bps_mean": 33.0,
                "period_pnl_mean": 0.04,
                "max_dd_mean": 0.000005,
            },
            {
                "symbol": "ETHUSDT",
                "timeframe": "15m",
                "strategy": "trend",
                "pf_mean": 2.5,
                "expectancy_bps_mean": 12.0,
                "period_pnl_mean": 1.2,
                "max_dd_mean": 0.02,
            },
            {
                "symbol": "XRPUSDT",
                "timeframe": "15m",
                "strategy": "trend",
                "pf_mean": 1.8,
                "expectancy_bps_mean": 3.0,
                "period_pnl_mean": 0.4,
                "max_dd_mean": 0.03,
            },
        ]
    }
    limit_summary = {
        "rows": [
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "strategy": "range",
                "pf_mean": 0.0,
                "expectancy_bps_mean": 0.0,
                "period_pnl_mean": 0.0,
                "max_dd_mean": 0.0,
            },
            {
                "symbol": "SOLUSDT",
                "timeframe": "15m",
                "strategy": "range",
                "pf_mean": 0.9,
                "expectancy_bps_mean": -5.0,
                "period_pnl_mean": 1.04,
                "max_dd_mean": 0.00054,
            },
            {
                "symbol": "XRPUSDT",
                "timeframe": "15m",
                "strategy": "range",
                "pf_mean": 0.8,
                "expectancy_bps_mean": -1.0,
                "period_pnl_mean": 0.04,
                "max_dd_mean": 0.000005,
            },
            {
                "symbol": "ETHUSDT",
                "timeframe": "15m",
                "strategy": "trend",
                "pf_mean": 2.5,
                "expectancy_bps_mean": 12.0,
                "period_pnl_mean": 1.2,
                "max_dd_mean": 0.02,
            },
        ]
    }
    symbol_gating = {
        "timeframe": "15m",
        "trend_enabled_symbols": ["ETHUSDT", "XRPUSDT"],
        "range_enabled_symbols": ["SOLUSDT", "XRPUSDT"],
    }
    candidate_report = {
        "core_symbols": ["SOLUSDT", "XRPUSDT"],
        "probe_symbols": ["ETHUSDT"],
        "watchlist_symbols": ["BTCUSDT"],
        "route_counts": {"core": 3, "probe": 1, "watchlist": 1},
        "symbol_counts": {"core": 2, "probe": 1, "watchlist": 1},
        "status": "pass",
    }
    drift_report = {
        "status": "pass",
        "drift_trade_block": False,
        "fail_feature_ratio": 0.0,
        "missing_feature_ratio": 0.0,
        "report_path": str(tmp_path / "drift.json"),
    }

    report = build_weekly_revalidation_report(
        market_summary,
        limit_summary,
        symbol_gating=symbol_gating,
        candidate_report=candidate_report,
        drift_report=drift_report,
        timeframe="15m",
    )

    assert report["status"] == "pass"
    assert report["market_status"] == "pass"
    assert report["limit_status"] == "warn"
    assert report["decision"]["market_reason"]["reason"] == "market criteria satisfied"
    assert report["decision"]["limit_reason"]["reason"].startswith("limit failed:")
    assert report["candidate_summary"]["core_count"] == 3
    assert report["candidate_summary"]["symbol_counts"]["core"] == 2
    assert (
        report["decision"]["candidate_reason"]["reason"]
        == "core routes=3, probe routes=1, watchlist routes=1"
    )
    assert report["selection"]["range_enabled_symbols"] == ["SOLUSDT", "XRPUSDT"]
    assert report["candidates"]["core_symbols"] == ["SOLUSDT", "XRPUSDT"]
    assert report["metrics"]["range"]["pf"] == 5.5
    assert report["metrics"]["range"]["exp_bps"] == 35.25
    assert report["limit_metrics"]["range"]["exp_bps"] == -3.0
