from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.analysis.revalidation import (
    apply_manifest_vs_weekly_diff_to_report,
    build_weekly_revalidation_report,
)


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
    statistical_report = {
        "status": "pass",
        "qualification_report_path": str(tmp_path / "qualification.json"),
        "passed_route_keys": [
            "trend:ETHUSDT:15m",
            "trend:XRPUSDT:15m",
            "range:SOLUSDT:15m",
            "range:XRPUSDT:15m",
        ],
        "routes": [],
    }

    report = build_weekly_revalidation_report(
        market_summary,
        limit_summary,
        symbol_gating=symbol_gating,
        candidate_report=candidate_report,
        drift_report=drift_report,
        statistical_report=statistical_report,
        timeframe="15m",
        run_id="weekly-123",
        generated_at="2026-06-13T00:00:00+00:00",
    )

    assert report["run_id"] == "weekly-123"
    assert report["generated_at"] == "2026-06-13T00:00:00+00:00"
    assert report["status"] == "pass"
    assert report["market_status"] == "pass"
    assert report["limit_status"] == "warn"
    assert report["decision"]["market_reason"]["reason"] == "market criteria satisfied"
    assert report["decision"]["limit_reason"]["reason"].startswith("limit failed:")
    assert report["candidate_summary"]["core_count"] == 3
    assert report["candidate_summary"]["symbol_counts"]["core"] == 2
    assert report["decision"]["candidate_reason"]["reason"] == "core routes=3, probe routes=1, watchlist routes=1"
    assert report["selection"]["range_enabled_symbols"] == ["SOLUSDT", "XRPUSDT"]
    assert report["candidates"]["core_symbols"] == ["SOLUSDT", "XRPUSDT"]
    assert report["metrics"]["range"]["pf"] == 5.5
    assert report["metrics"]["range"]["exp_bps"] == 35.25
    assert report["limit_metrics"]["range"]["exp_bps"] == -3.0
    assert report["overview"]["trend_performance"]["pf"] == 2.15
    assert report["overview"]["range_performance"]["pf"] == 5.5
    assert report["feature_drift"]["status"] == "pass"
    assert report["statistical_qualification"]["status"] == "pass"


def test_weekly_revalidation_uses_route_selection_manifest_for_mixed_timeframes(
    tmp_path: Path,
) -> None:
    market_summary = {
        "rows": [
            {
                "symbol": "BNBUSDT",
                "timeframe": "1h",
                "strategy": "trend",
                "pf_mean": 1.34,
                "expectancy_bps_mean": 18.23,
                "period_pnl_mean": 7.85,
                "max_dd_mean": 0.003,
            },
            {
                "symbol": "SOLUSDT",
                "timeframe": "30m",
                "strategy": "range",
                "pf_mean": 1.22,
                "expectancy_bps_mean": 6.1,
                "period_pnl_mean": 1.8,
                "max_dd_mean": 0.04,
            },
            {
                "symbol": "BNBUSDT",
                "timeframe": "15m",
                "strategy": "trend",
                "pf_mean": 0.1,
                "expectancy_bps_mean": -50.0,
                "period_pnl_mean": -10.0,
                "max_dd_mean": 0.5,
            },
        ]
    }
    report = build_weekly_revalidation_report(
        market_summary,
        {"rows": []},
        symbol_gating={"trend_enabled_symbols": [], "range_enabled_symbols": []},
        candidate_report={"status": "pass"},
        drift_report={"status": "pass"},
        statistical_report={"status": "pass", "passed_route_keys": []},
        route_selection={
            "selection": {
                "trade_routes": [
                    {
                        "symbol": "BNBUSDT",
                        "strategy": "trend",
                        "timeframe": "1h",
                        "expected_regime": "TREND",
                        "candidate_status": "core",
                        "statistical_status": "pass",
                    },
                    {
                        "symbol": "SOLUSDT",
                        "strategy": "range",
                        "timeframe": "30m",
                        "expected_regime": "RANGE",
                        "candidate_status": "core",
                        "statistical_status": "pass",
                    },
                ]
            }
        },
        timeframe="15m",
    )

    assert report["selection"]["route_selection_source"] == "manifest"
    assert report["metrics"]["trend"]["pf"] == 1.34
    assert report["metrics"]["range"]["pf"] == 1.22


def test_weekly_revalidation_reports_portfolio_and_selection_bias(
    tmp_path: Path,
) -> None:
    market_summary = {
        "rows": [
            {
                "symbol": "ETHUSDT",
                "timeframe": "1h",
                "strategy": "trend",
                "pf_mean": 1.8,
                "expectancy_bps_mean": 16.0,
                "period_pnl_mean": 58.0,
                "max_dd_mean": 0.01,
            },
            {
                "symbol": "SOLUSDT",
                "timeframe": "30m",
                "strategy": "range",
                "pf_mean": 1.3,
                "expectancy_bps_mean": 5.0,
                "period_pnl_mean": 2.3,
                "max_dd_mean": 0.001,
            },
        ]
    }
    report = build_weekly_revalidation_report(
        market_summary,
        {"rows": []},
        symbol_gating={"trend_enabled_symbols": [], "range_enabled_symbols": []},
        candidate_report={"status": "pass"},
        drift_report={"status": "pass"},
        statistical_report={
            "status": "pass",
            "passed_route_keys": ["trend:ETHUSDT:1h", "range:SOLUSDT:30m"],
        },
        route_selection={
            "selection": {
                "trade_routes": [
                    {
                        "symbol": "ETHUSDT",
                        "strategy": "trend",
                        "timeframe": "1h",
                        "expected_regime": "TREND",
                        "candidate_status": "core",
                        "statistical_status": "pass",
                    },
                    {
                        "symbol": "SOLUSDT",
                        "strategy": "range",
                        "timeframe": "30m",
                        "expected_regime": "RANGE",
                        "candidate_status": "core",
                        "statistical_status": "pass",
                    },
                ]
            }
        },
        timeframe="15m",
    )

    assert report["portfolio_qualification"]["status"] == "pass"
    assert report["portfolio_qualification"]["qualified_route_count"] == 2
    assert report["portfolio_qualification"]["qualified_strategy_count"] == 2
    assert report["portfolio_qualification"]["missing_route_count"] == 0
    assert report["portfolio_qualification"]["missing_strategy_count"] == 0
    assert report["portfolio_qualification"]["strategy_breakdown"]["trend"]["qualified_route_count"] == 1
    assert report["portfolio_qualification"]["strategy_breakdown"]["range"]["qualified_route_count"] == 1
    assert report["portfolio_strategy_actions"]["trend"]["recommendation"] == "bundle_pass"
    assert report["portfolio_strategy_actions"]["range"]["recommendation"] == "bundle_pass"
    assert report["portfolio_strategy_priority_summary"]["trend"]["priority_route_keys"] == ["trend:ETHUSDT:1h"]
    assert report["portfolio_strategy_priority_summary"]["range"]["priority_route_keys"] == ["range:SOLUSDT:30m"]
    assert report["overview"]["portfolio_strategy_priority_summary"]["trend"]["priority_route_keys"] == ["trend:ETHUSDT:1h"]
    assert report["selection_bias_audit"]["status"] == "pass"
    assert report["overview"]["portfolio_status"] == "pass"
    assert report["overview"]["portfolio_qualification_summary"]["qualified_strategy_count"] == 2
    assert report["overview"]["portfolio_qualification_summary"]["required_route_count"] == 2
    assert report["overview"]["portfolio_qualification_summary"]["required_strategy_count"] == 2
    assert report["overview"]["portfolio_qualification_summary"]["missing_route_count"] == 0
    assert report["overview"]["portfolio_qualification_summary"]["missing_strategy_count"] == 0
    assert report["overview"]["portfolio_qualification_summary"]["reasons"] == []
    assert report["overview"]["portfolio_qualification_summary"]["selected_route_keys"] == [
        "trend:ETHUSDT:1h",
        "range:SOLUSDT:30m",
    ]
    assert report["overview"]["portfolio_qualification_summary"]["qualified_route_keys"] == [
        "trend:ETHUSDT:1h",
        "range:SOLUSDT:30m",
    ]
    assert report["overview"]["portfolio_strategy_actions"]["trend"]["qualified_route_count"] == 1
    assert report["overview"]["portfolio_strategy_actions"]["range"]["recommendation"] == "bundle_pass"
    assert report["overview"]["portfolio_next_action_summary"]["trend"]["recommendation"] == "bundle_pass"
    assert report["overview"]["portfolio_next_action_route_keys"] == [
        "trend:ETHUSDT:1h",
        "range:SOLUSDT:30m",
    ]
    assert report["overview"]["portfolio_qualification_gap_summary"]["required_route_count"] == 2
    assert report["overview"]["portfolio_qualification_gap_summary"]["required_strategy_count"] == 2
    assert report["overview"]["selection_bias_status"] == "pass"
    assert report["overview"]["selection_bias_final_holdout_summary"]["status"] == "missing"


def test_weekly_revalidation_flags_selection_bias_when_route_is_unqualified(
    tmp_path: Path,
) -> None:
    report = build_weekly_revalidation_report(
        {"rows": []},
        {"rows": []},
        symbol_gating={"trend_enabled_symbols": [], "range_enabled_symbols": []},
        candidate_report={"status": "pass"},
        drift_report={"status": "pass"},
        statistical_report={"status": "pass", "passed_route_keys": ["trend:ETHUSDT:1h"]},
        route_selection={
            "selection": {
                "trade_routes": [
                    {
                        "symbol": "ETHUSDT",
                        "strategy": "trend",
                        "timeframe": "1h",
                        "expected_regime": "TREND",
                        "candidate_status": "core",
                        "statistical_status": "pass",
                    },
                    {
                        "symbol": "SOLUSDT",
                        "strategy": "range",
                        "timeframe": "30m",
                        "expected_regime": "RANGE",
                        "candidate_status": "core",
                        "statistical_status": "fail",
                    },
                ]
            }
        },
        timeframe="15m",
    )

    assert report["portfolio_qualification"]["status"] == "fail"
    assert "contains_non_qualified_routes" in report["portfolio_qualification"]["reasons"]
    assert "qualified_route_count_lt_2" in report["portfolio_qualification"]["reasons"]
    assert report["portfolio_qualification"]["missing_route_count"] == 1
    assert report["portfolio_qualification"]["missing_strategy_count"] == 1
    assert report["portfolio_qualification"]["strategy_breakdown"]["trend"]["qualified_route_count"] == 1
    assert report["portfolio_qualification"]["strategy_breakdown"]["range"]["qualified_route_count"] == 0
    assert report["portfolio_strategy_actions"]["trend"]["recommendation"] == "bundle_pass"
    assert report["portfolio_strategy_actions"]["range"]["recommendation"] == "bundle_review"
    assert report["portfolio_strategy_priority_summary"]["trend"]["priority_route_keys"] == ["trend:ETHUSDT:1h"]
    assert report["portfolio_strategy_priority_summary"]["range"]["priority_route_keys"] == ["range:SOLUSDT:30m"]
    assert report["overview"]["portfolio_strategy_priority_summary"]["range"]["priority_route_keys"] == ["range:SOLUSDT:30m"]
    assert report["selection_bias_audit"]["status"] == "warn"
    assert report["selection_bias_audit"]["unqualified_route_keys"] == ["range:SOLUSDT:30m"]
    assert report["overview"]["portfolio_strategy_actions"]["range"]["recommendation"] == "bundle_review"
    assert report["overview"]["portfolio_next_action_summary"]["trend"]["accumulate_oos_route_keys"] == ["trend:ETHUSDT:1h"]
    assert report["overview"]["portfolio_next_action_summary"]["range"]["drop_or_retune_route_keys"] == ["range:SOLUSDT:30m"]
    assert report["overview"]["portfolio_next_action_route_keys"] == [
        "trend:ETHUSDT:1h",
        "range:SOLUSDT:30m",
    ]
    assert report["overview"]["portfolio_qualification_summary"]["missing_route_count"] == 1
    assert report["overview"]["portfolio_qualification_summary"]["missing_strategy_count"] == 1
    assert report["overview"]["portfolio_qualification_gap_summary"]["required_route_count"] == 2
    assert report["overview"]["portfolio_qualification_gap_summary"]["required_strategy_count"] == 2
    assert report["overview"]["portfolio_qualification_gap_summary"]["next_route_keys"] == [
        "trend:ETHUSDT:1h",
        "range:SOLUSDT:30m",
    ]
    assert report["overview"]["portfolio_qualification_summary"]["selected_route_keys"] == [
        "trend:ETHUSDT:1h",
        "range:SOLUSDT:30m",
    ]
    assert report["overview"]["portfolio_qualification_summary"]["qualified_route_keys"] == [
        "trend:ETHUSDT:1h",
    ]
    assert "contains_non_qualified_routes" in report["overview"]["portfolio_qualification_summary"]["reasons"]


def test_weekly_revalidation_uses_manifest_vs_weekly_holdout_for_selection_bias(
    tmp_path: Path,
) -> None:
    report = build_weekly_revalidation_report(
        {"rows": []},
        {"rows": []},
        symbol_gating={"trend_enabled_symbols": [], "range_enabled_symbols": []},
        candidate_report={"status": "pass"},
        drift_report={"status": "pass"},
        statistical_report={"status": "pass", "passed_route_keys": ["trend:ETHUSDT:1h"]},
        route_selection={
            "selection": {
                "trade_routes": [
                    {
                        "symbol": "ETHUSDT",
                        "strategy": "trend",
                        "timeframe": "1h",
                        "expected_regime": "TREND",
                        "candidate_status": "core",
                        "statistical_status": "pass",
                    }
                ]
            }
        },
        manifest_vs_weekly_diff={
            "rows": [
                {
                    "route_key": "trend:ETHUSDT:1h",
                    "strategy": "trend",
                    "source": {
                        "final_oos": {
                            "fold": 3,
                            "pf": 1.5,
                            "expectancy_bps": 10.0,
                            "period_pnl": 3.0,
                            "max_dd": 0.02,
                            "closed_trades": 20.0,
                        }
                    },
                    "weekly": {
                        "final_oos": {
                            "fold": 3,
                            "pf": 1.45,
                            "expectancy_bps": 8.0,
                            "period_pnl": 2.5,
                            "max_dd": 0.025,
                            "closed_trades": 20.0,
                        }
                    },
                }
            ]
        },
        timeframe="15m",
    )

    assert report["selection_bias_audit"]["status"] == "pass"
    assert report["selection_bias_audit"]["final_holdout_audit"]["status"] == "pass"
    assert report["selection_bias_audit"]["final_holdout_audit"]["paired_route_count"] == 1
    assert report["selection_bias_audit"]["final_holdout_audit"]["route_deltas"][0]["delta"]["expectancy_bps"] == -2.0
    assert report["selection_bias_audit"]["final_holdout_audit"]["strategy_deltas"]["trend"]["route_count"] == 1
    assert report["selection_bias_audit"]["final_holdout_summary"]["paired_route_count"] == 1
    assert report["selection_bias_audit"]["final_holdout_summary"]["avg_delta_expectancy_bps"] == -2.0
    assert report["selection_bias_audit"]["final_holdout_summary"]["strategy_summary"]["trend"]["route_count"] == 1
    assert report["overview"]["selection_bias_final_holdout_summary"]["paired_route_count"] == 1
    assert report["overview"]["selection_bias_final_holdout_strategy_summary"]["trend"]["route_count"] == 1


def test_apply_manifest_vs_weekly_diff_to_report_refreshes_holdout_summary() -> None:
    report = {
        "selection": {
            "trade_routes": [
                {
                    "symbol": "ETHUSDT",
                    "strategy": "trend",
                    "timeframe": "1h",
                },
                {
                    "symbol": "SOLUSDT",
                    "strategy": "range",
                    "timeframe": "30m",
                },
            ]
        },
        "statistical_qualification": {"passed_route_keys": ["trend:ETHUSDT:1h", "range:SOLUSDT:30m"]},
        "overview": {"selection_bias_status": "warn"},
    }
    diff = {
        "rows": [
            {
                "route_key": "trend:ETHUSDT:1h",
                "strategy": "trend",
                "source": {
                    "fold_snapshot": {
                        "final_oos": {
                            "pf": 1.5,
                            "expectancy_bps": 10.0,
                            "period_pnl": 3.0,
                            "max_dd": 0.02,
                            "closed_trades": 20.0,
                        }
                    }
                },
                "weekly": {
                    "fold_snapshot": {
                        "final_oos": {
                            "pf": 1.4,
                            "expectancy_bps": 9.0,
                            "period_pnl": 2.0,
                            "max_dd": 0.03,
                            "closed_trades": 21.0,
                        }
                    }
                },
            },
            {
                "route_key": "range:SOLUSDT:30m",
                "strategy": "range",
                "source": {
                    "fold_snapshot": {
                        "final_oos": {
                            "pf": 1.2,
                            "expectancy_bps": 5.0,
                            "period_pnl": 1.0,
                            "max_dd": 0.01,
                            "closed_trades": 18.0,
                        }
                    }
                },
                "weekly": {
                    "fold_snapshot": {
                        "final_oos": {
                            "pf": 1.1,
                            "expectancy_bps": 4.0,
                            "period_pnl": 0.5,
                            "max_dd": 0.02,
                            "closed_trades": 19.0,
                        }
                    }
                },
            },
        ]
    }

    refreshed = apply_manifest_vs_weekly_diff_to_report(report, diff)

    assert refreshed["selection_bias_audit"]["status"] == "pass"
    assert refreshed["selection_bias_audit"]["final_holdout_audit"]["paired_route_count"] == 2
    assert set(refreshed["selection_bias_audit"]["final_holdout_audit"]["strategy_deltas"]) == {
        "trend",
        "range",
    }
    assert refreshed["selection_bias_audit"]["final_holdout_summary"]["strategy_summary"]["trend"]["route_count"] == 1
    assert refreshed["overview"]["selection_bias_status"] == "pass"
    assert refreshed["overview"]["selection_bias_final_holdout_strategy_summary"]["range"]["route_count"] == 1


def test_weekly_revalidation_reports_portfolio_risk_audit(tmp_path: Path) -> None:
    report = build_weekly_revalidation_report(
        {"rows": []},
        {"rows": []},
        symbol_gating={"trend_enabled_symbols": [], "range_enabled_symbols": []},
        candidate_report={"status": "pass"},
        drift_report={"status": "pass"},
        statistical_report={"status": "pass", "passed_route_keys": ["trend:ETHUSDT:1h"]},
        route_selection={
            "selection": {
                "trade_routes": [
                    {
                        "symbol": "ETHUSDT",
                        "strategy": "trend",
                        "timeframe": "1h",
                        "expected_regime": "TREND",
                        "candidate_status": "core",
                        "statistical_status": "pass",
                    }
                ]
            }
        },
        portfolio_risk_eval={
            "rows": [
                {
                    "timestamp": "2026-06-13T00:00:00+00:00",
                    "symbol": "ETHUSDT",
                    "risk_blocked": False,
                    "block_reason_codes": ["RISK_OK"],
                    "current_dd_pct": 8.5,
                    "portfolio_exposure_pct": 42.0,
                    "concentration_score": 0.35,
                    "correlated_exposure_pct": 38.0,
                    "vol_weighted_exposure_pct": 41.0,
                    "risk_contribution_pct": 33.0,
                    "missing_vol_ratio": 0.0,
                    "size_scale": 1.0,
                    "emergency_state": False,
                }
            ]
        },
        timeframe="15m",
    )

    assert report["portfolio_risk_audit"]["status"] == "pass"
    assert report["portfolio_risk_audit"]["latest_timestamp"] == "2026-06-13T00:00:00+00:00"
    assert report["portfolio_risk_audit"]["symbol_count"] == 1
    assert report["overview"]["portfolio_risk_status"] == "pass"


def test_weekly_revalidation_reads_portfolio_risk_eval_parquet(tmp_path: Path) -> None:
    risk_eval = tmp_path / "risk_eval.parquet"
    pd.DataFrame(
        [
            {
                "timestamp": "2026-06-13T00:00:00+00:00",
                "symbol": "ETHUSDT",
                "risk_blocked": False,
                "block_reason_codes": ["RISK_OK"],
                "current_dd_pct": 4.0,
                "portfolio_exposure_pct": 30.0,
                "concentration_score": 0.2,
                "correlated_exposure_pct": 25.0,
                "vol_weighted_exposure_pct": 20.0,
                "risk_contribution_pct": 15.0,
                "missing_vol_ratio": 0.0,
                "size_scale": 1.0,
                "emergency_state": False,
            }
        ]
    ).to_parquet(risk_eval, index=False)

    report = build_weekly_revalidation_report(
        {"rows": []},
        {"rows": []},
        symbol_gating={"trend_enabled_symbols": [], "range_enabled_symbols": []},
        candidate_report={"status": "pass"},
        drift_report={"status": "pass"},
        statistical_report={"status": "pass", "passed_route_keys": ["trend:ETHUSDT:1h"]},
        route_selection={
            "selection": {
                "trade_routes": [
                    {
                        "symbol": "ETHUSDT",
                        "strategy": "trend",
                        "timeframe": "1h",
                        "expected_regime": "TREND",
                        "candidate_status": "core",
                        "statistical_status": "pass",
                    }
                ]
            }
        },
        portfolio_risk_eval=risk_eval,
        timeframe="15m",
    )

    assert report["portfolio_risk_audit"]["status"] == "pass"
    assert report["portfolio_risk_audit"]["symbol_count"] == 1
    assert report["portfolio_risk_audit"]["risk_blocked_count"] == 0


def test_weekly_revalidation_warns_when_holdout_is_missing(tmp_path: Path) -> None:
    report = build_weekly_revalidation_report(
        {"rows": []},
        {"rows": []},
        symbol_gating={"trend_enabled_symbols": [], "range_enabled_symbols": []},
        candidate_report={"status": "pass"},
        drift_report={"status": "pass"},
        statistical_report={"status": "pass", "passed_route_keys": ["trend:ETHUSDT:1h"]},
        route_selection={
            "selection": {
                "trade_routes": [
                    {
                        "symbol": "ETHUSDT",
                        "strategy": "trend",
                        "timeframe": "1h",
                        "expected_regime": "TREND",
                        "candidate_status": "core",
                        "statistical_status": "pass",
                    }
                ]
            }
        },
        manifest_vs_weekly_diff={
            "rows": [
                {
                    "route_key": "trend:ETHUSDT:1h",
                    "source": {"final_oos": {"fold": 3, "pf": 1.5}},
                    "weekly": {"final_oos": {}},
                }
            ]
        },
        timeframe="15m",
    )

    assert report["selection_bias_audit"]["status"] == "warn"
    assert "missing_weekly_final_oos" in report["selection_bias_audit"]["reasons"]
    assert report["selection_bias_audit"]["final_holdout_summary"]["status"] == "warn"
    assert report["selection_bias_audit"]["final_holdout_summary"]["strategy_summary"] == {}


def test_weekly_revalidation_classifies_sample_thin_routes(tmp_path: Path) -> None:
    report = build_weekly_revalidation_report(
        {"rows": []},
        {"rows": []},
        symbol_gating={"trend_enabled_symbols": [], "range_enabled_symbols": []},
        candidate_report={"status": "pass"},
        drift_report={"status": "pass"},
        statistical_report={
            "status": "fail",
            "routes": [
                {
                    "route_key": "trend:ADAUSDT:30m",
                    "status": "fail",
                    "reasons": ["min_route_trades", "pf"],
                },
                {
                    "route_key": "trend:ETHUSDT:1h",
                    "status": "fail",
                    "reasons": ["pf", "expectancy_bps", "mc_loss_probability"],
                },
                {
                    "route_key": "range:SOLUSDT:30m",
                    "status": "pass",
                    "reasons": [],
                },
            ],
        },
        timeframe="15m",
    )

    assert report["route_quality_audit"]["status"] == "warn"
    assert report["route_quality_audit"]["sample_thin_route_keys"] == ["trend:ADAUSDT:30m"]
    assert report["route_quality_audit"]["oos_quality_route_keys"] == ["trend:ETHUSDT:1h"]
    assert report["route_quality_audit"]["route_actions"][0]["recommendation"] == "accumulate_oos"
    assert report["route_quality_audit"]["route_actions"][1]["recommendation"] == "drop_or_retune"
    assert report["route_quality_audit"]["strategy_counts"]["trend"]["total"] == 2
    assert report["route_quality_audit"]["strategy_counts"]["range"]["total"] == 1
    assert report["route_quality_summary"]["recommendations"]["accumulate_oos"] == 1
    assert report["route_quality_summary"]["recommendations"]["drop_or_retune"] == 1
    assert report["route_priority_summary"]["priority_route_keys"] == [
        "trend:ADAUSDT:30m",
        "trend:ETHUSDT:1h",
    ]
    assert report["overview"]["route_quality_summary"]["sample_thin_count"] == 1
    assert report["strategy_quality_summary"]["trend"]["recommendation"] == "drop_or_retune"
    assert report["strategy_quality_summary"]["range"]["recommendation"] == "monitor"
    assert report["overview"]["route_quality_status"] == "warn"
