from __future__ import annotations

import json
from pathlib import Path

from auto_trader.analysis.autotune_feedback import (
    build_autotune_feedback,
    build_full_route_manifest,
    build_route_manifest,
    render_manifest_markdown,
    render_markdown,
)


def test_build_autotune_feedback_preserves_selection_mode(tmp_path: Path) -> None:
    summary_path = tmp_path / "auto_tune_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "selection_mode": "core_refinement",
                "out_dir": "data/validation/core_route_refinement_run1",
                "route_summaries": [
                    {
                        "route": "trend:BNBUSDT:1h",
                        "selected_stage": "trend_next_step",
                        "final_state": "core_confirmed",
                        "selected": {
                            "candidate_status": "core",
                            "config_label": "cooldown0_exit0.02",
                            "pf_mean": 1.34,
                            "expectancy_bps_mean": 18.23,
                            "period_pnl_mean": 7.858,
                            "max_dd_mean": 0.0037,
                            "closed_trades_mean": 10.75,
                        },
                        "stages": [
                            {
                                "stage": "trend_next_step",
                                "best": {"config_label": "cooldown0_exit0.02"},
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    feedback = build_autotune_feedback(summary_path)

    assert feedback["selection_mode"] == "core_refinement"
    assert feedback["trade_routes"][0]["selected_stage"] == "trend_next_step"


def test_build_full_route_manifest_overwrites_matching_baseline_core_for_refinement(
    tmp_path: Path,
) -> None:
    baseline_candidate_report = tmp_path / "candidate_report.json"
    baseline_candidate_report.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "symbol": "BNBUSDT",
                        "strategy": "trend",
                        "timeframe": "1h",
                        "candidate_status": "core",
                        "pf_mean": 1.213,
                        "expectancy_bps_mean": 7.44,
                        "period_pnl_mean": 0.822,
                        "max_dd_mean": 0.00367,
                        "closed_trades_mean": 11.75,
                    },
                    {
                        "symbol": "ADAUSDT",
                        "strategy": "trend",
                        "timeframe": "30m",
                        "candidate_status": "core",
                        "pf_mean": 1.687,
                        "expectancy_bps_mean": 10.94,
                        "period_pnl_mean": 0.009,
                        "max_dd_mean": 0.0,
                        "closed_trades_mean": 13.0,
                    },
                ]
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    summary_path = tmp_path / "auto_tune_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "selection_mode": "core_refinement",
                "baseline_candidate_report": str(baseline_candidate_report),
                "route_summaries": [
                    {
                        "route": "trend:BNBUSDT:1h",
                        "selected_stage": "trend_next_step",
                        "final_state": "core_confirmed",
                        "selected": {
                            "candidate_status": "core",
                            "config_label": "cooldown0_exit0.02",
                            "pf_mean": 1.340,
                            "expectancy_bps_mean": 18.23,
                            "period_pnl_mean": 7.858,
                            "max_dd_mean": 0.00374,
                            "closed_trades_mean": 10.75,
                        },
                        "stages": [
                            {
                                "stage": "trend_next_step",
                                "best": {"config_label": "cooldown0_exit0.02"},
                            },
                            {
                                "stage": "regime_threshold",
                                "best": {"config_label": "adx25_breakouthold2_regimehold1_hvcool5"},
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    feedback = build_autotune_feedback(summary_path)
    full_manifest = build_full_route_manifest(feedback)

    assert full_manifest["selection_mode"] == "core_refinement"
    routes = full_manifest["selection"]["trade_routes"]
    bnb_routes = [row for row in routes if row["symbol"] == "BNBUSDT" and row["timeframe"] == "1h"]
    assert len(bnb_routes) == 1
    assert bnb_routes[0]["selection_source"] == "autotune"
    assert bnb_routes[0]["selected_stage"] == "trend_next_step"
    assert float(bnb_routes[0]["pf_mean"]) == 1.340
    assert bnb_routes[0]["params"]["trend_reentry_cooldown_bars"] == 0
    assert bnb_routes[0]["params"]["trend_efficiency_exit_threshold"] == 0.02

    ada_routes = [row for row in routes if row["symbol"] == "ADAUSDT" and row["timeframe"] == "30m"]
    assert len(ada_routes) == 1
    assert ada_routes[0]["selection_source"] == "baseline_core"


def test_render_markdown_mentions_refinement_delta() -> None:
    feedback = {
        "generated_at": "2026-06-12T00:00:00+00:00",
        "summary_path": "summary.json",
        "source_out_dir": "data/validation/core_route_refinement_run1",
        "selection_mode": "core_refinement",
        "route_count": 1,
        "symbols": ["BNBUSDT"],
        "trend_enabled_symbols": ["BNBUSDT"],
        "range_enabled_symbols": [],
        "trade_routes": [],
    }

    text = render_markdown(feedback)
    assert "selection_mode: core_refinement" in text
    assert "refinement delta" in text


def test_render_manifest_markdown_mentions_refinement_overwrite() -> None:
    manifest = {
        "generated_at": "2026-06-12T00:00:00+00:00",
        "source": "autotune_feedback_full",
        "selection_mode": "core_refinement",
        "selection": {
            "trend_enabled_symbols": ["BNBUSDT"],
            "range_enabled_symbols": [],
            "trade_routes": [],
        },
    }

    text = render_manifest_markdown(manifest)
    assert "selection_mode: core_refinement" in text
    assert "overwritten by refinement-selected routes" in text


def test_build_route_manifest_preserves_selection_mode() -> None:
    manifest = build_route_manifest(
        {
            "selection_mode": "core_refinement",
            "trend_enabled_symbols": ["BNBUSDT"],
            "range_enabled_symbols": [],
            "trade_routes": [
                {
                    "symbol": "BNBUSDT",
                    "strategy": "trend",
                    "timeframe": "1h",
                    "candidate_status": "core",
                    "selected_stage": "trend_next_step",
                    "config_label": "cooldown0_exit0.02",
                    "pf_mean": 1.34,
                    "expectancy_bps_mean": 18.23,
                    "period_pnl_mean": 7.858,
                    "max_dd_mean": 0.00374,
                    "closed_trades_mean": 10.75,
                    "params": {"trend_reentry_cooldown_bars": 0},
                }
            ],
        }
    )

    assert manifest["selection_mode"] == "core_refinement"
    assert manifest["selection"]["trade_routes"][0]["selection_source"] == "autotune"


def test_build_full_route_manifest_keeps_expansion_routes_when_refining(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "auto_tune_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "selection_mode": "core_refinement",
                "route_summaries": [
                    {
                        "route": "trend:BNBUSDT:1h",
                        "selected_stage": "trend_next_step",
                        "final_state": "core_confirmed",
                        "selected": {
                            "candidate_status": "core",
                            "config_label": "cooldown0_exit0.02",
                            "pf_mean": 1.34,
                            "expectancy_bps_mean": 18.23,
                            "period_pnl_mean": 7.858,
                            "max_dd_mean": 0.00374,
                            "closed_trades_mean": 10.75,
                        },
                        "stages": [
                            {
                                "stage": "trend_next_step",
                                "best": {"config_label": "cooldown0_exit0.02"},
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    base_manifest_path = tmp_path / "expansion_full_manifest.json"
    base_manifest_path.write_text(
        json.dumps(
            {
                "selection_mode": "expansion",
                "selection": {
                    "trade_routes": [
                        {
                            "symbol": "SOLUSDT",
                            "strategy": "range",
                            "timeframe": "30m",
                            "expected_regime": "RANGE",
                            "candidate_status": "core",
                            "statistical_status": "pass",
                            "selection_source": "autotune",
                            "selected_stage": "range_matrix",
                            "config_label": "wick0.2_reversalfalse_cooldown2",
                            "pf_mean": 1.22,
                            "expectancy_bps_mean": 6.1,
                            "period_pnl_mean": 1.8,
                            "max_dd_mean": 0.04,
                            "closed_trades_mean": 22.0,
                            "params": {"range_reentry_cooldown_bars": 2},
                        },
                        {
                            "symbol": "BNBUSDT",
                            "strategy": "trend",
                            "timeframe": "1h",
                            "expected_regime": "TREND",
                            "candidate_status": "core",
                            "statistical_status": "pass",
                            "selection_source": "baseline_core",
                            "selected_stage": "baseline",
                            "config_label": "baseline",
                            "pf_mean": 1.213,
                            "expectancy_bps_mean": 7.44,
                            "period_pnl_mean": 0.822,
                            "max_dd_mean": 0.00367,
                            "closed_trades_mean": 11.75,
                            "params": {},
                        },
                    ]
                },
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    feedback = build_autotune_feedback(summary_path)
    full_manifest = build_full_route_manifest(feedback, base_manifest=base_manifest_path)

    routes = full_manifest["selection"]["trade_routes"]
    assert len(routes) == 2
    assert {f"{row['strategy']}:{row['symbol']}:{row['timeframe']}" for row in routes} == {
        "range:SOLUSDT:30m",
        "trend:BNBUSDT:1h",
    }
    bnb_route = next(row for row in routes if row["symbol"] == "BNBUSDT")
    assert bnb_route["selection_source"] == "autotune"
    sol_route = next(row for row in routes if row["symbol"] == "SOLUSDT")
    assert sol_route["selection_source"] == "autotune"
    assert full_manifest["base_manifest_path"] == str(base_manifest_path)
