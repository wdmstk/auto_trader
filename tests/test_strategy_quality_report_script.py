from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _run_script(repo_root: Path, env: dict[str, str]) -> None:
    subprocess.run(
        ["bash", "scripts/strategy_quality_report.sh"],
        cwd=repo_root,
        env={**os.environ, **env},
        check=True,
        capture_output=True,
        text=True,
    )


def test_strategy_quality_report_renders_strategy_sections(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "weekly_revalidation_report.json"
    out_path = tmp_path / "strategy_quality_report.md"
    report_path.write_text(
        json.dumps(
            {
                "overview": {
                    "portfolio_status": "fail",
                    "strategy_quality_summary": {
                        "range": {
                            "total": 1,
                            "sample_thin_count": 0,
                            "oos_quality_count": 1,
                            "recommendation": "drop_or_retune",
                        },
                        "trend": {
                            "total": 5,
                            "sample_thin_count": 4,
                            "oos_quality_count": 1,
                            "recommendation": "drop_or_retune",
                        },
                    },
                    "portfolio_strategy_priority_summary": {
                        "range": {
                            "recommendation": "bundle_review",
                            "priority_route_keys": ["range:SOLUSDT:30m"],
                        },
                        "trend": {
                            "recommendation": "bundle_review",
                            "priority_route_keys": [
                                "trend:ADAUSDT:1h",
                                "trend:ADAUSDT:30m",
                                "trend:BNBUSDT:1h",
                                "trend:ETHUSDT:1h",
                                "trend:SOLUSDT:15m",
                            ],
                        },
                    },
                    "portfolio_next_action_summary": {
                        "range": {
                            "selected_route_count": 1,
                            "qualified_route_count": 0,
                            "recommendation": "bundle_review",
                            "accumulate_oos_route_keys": [],
                            "drop_or_retune_route_keys": ["range:SOLUSDT:30m"],
                        },
                        "trend": {
                            "selected_route_count": 5,
                            "qualified_route_count": 0,
                            "recommendation": "bundle_review",
                            "accumulate_oos_route_keys": [
                                "trend:ADAUSDT:1h",
                                "trend:ADAUSDT:30m",
                                "trend:BNBUSDT:1h",
                                "trend:ETHUSDT:1h",
                            ],
                            "drop_or_retune_route_keys": ["trend:SOLUSDT:15m"],
                        },
                    },
                },
                "selection_bias_audit": {
                    "final_holdout_summary": {
                        "strategy_summary": {
                            "range": {
                                "route_count": 1,
                                "avg_delta_pf": 0.1,
                                "avg_delta_expectancy_bps": 2.0,
                                "avg_delta_period_pnl": 0.3,
                                "avg_delta_max_dd": -0.02,
                                "avg_delta_closed_trades": 4.0,
                            },
                            "trend": {
                                "route_count": 5,
                                "avg_delta_pf": -0.2,
                                "avg_delta_expectancy_bps": -3.0,
                                "avg_delta_period_pnl": -0.4,
                                "avg_delta_max_dd": 0.05,
                                "avg_delta_closed_trades": -1.0,
                            },
                        }
                    }
                },
                "route_quality_audit": {
                    "route_actions": [
                        {
                            "route_key": "range:SOLUSDT:30m",
                            "strategy": "range",
                            "recommendation": "drop_or_retune",
                        },
                        {
                            "route_key": "trend:ADAUSDT:1h",
                            "strategy": "trend",
                            "recommendation": "accumulate_oos",
                        },
                        {
                            "route_key": "trend:ADAUSDT:30m",
                            "strategy": "trend",
                            "recommendation": "accumulate_oos",
                        },
                        {
                            "route_key": "trend:BNBUSDT:1h",
                            "strategy": "trend",
                            "recommendation": "accumulate_oos",
                        },
                        {
                            "route_key": "trend:ETHUSDT:1h",
                            "strategy": "trend",
                            "recommendation": "accumulate_oos",
                        },
                        {
                            "route_key": "trend:SOLUSDT:15m",
                            "strategy": "trend",
                            "recommendation": "drop_or_retune",
                        },
                    ],
                },
                "statistical_qualification": {
                    "routes": [
                        {
                            "route_key": "range:SOLUSDT:30m",
                            "strategy": "range",
                            "status": "fail",
                            "metrics": {"closed_trades": 37},
                        },
                        {
                            "route_key": "trend:ADAUSDT:1h",
                            "strategy": "trend",
                            "status": "fail",
                            "metrics": {"closed_trades": 6},
                        },
                        {
                            "route_key": "trend:ADAUSDT:30m",
                            "strategy": "trend",
                            "status": "fail",
                            "metrics": {"closed_trades": 16},
                        },
                        {
                            "route_key": "trend:BNBUSDT:1h",
                            "strategy": "trend",
                            "status": "fail",
                            "metrics": {"closed_trades": 7},
                        },
                        {
                            "route_key": "trend:ETHUSDT:1h",
                            "strategy": "trend",
                            "status": "fail",
                            "metrics": {"closed_trades": 5},
                        },
                        {
                            "route_key": "trend:SOLUSDT:15m",
                            "strategy": "trend",
                            "status": "fail",
                            "metrics": {"closed_trades": 38},
                        },
                    ]
                },
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    _run_script(
        repo_root,
        {
            "REPORT_PATH": str(report_path),
            "OUT_PATH": str(out_path),
        },
    )

    rendered = out_path.read_text(encoding="utf-8")
    assert "# Strategy Quality Report" in rendered
    assert "| range | 1 | 0 | 1 | drop_or_retune |" in rendered
    assert "| trend | 5 | 4 | 1 | drop_or_retune |" in rendered
    assert "range:SOLUSDT:30m" in rendered
    assert "trend:ADAUSDT:1h, trend:ADAUSDT:30m, trend:BNBUSDT:1h, trend:ETHUSDT:1h, trend:SOLUSDT:15m" in rendered
    assert "| range | 1 | 0 | bundle_review | - | range:SOLUSDT:30m |" in rendered
    assert "| trend | 5 | 0 | bundle_review | trend:ADAUSDT:1h, trend:ADAUSDT:30m, trend:BNBUSDT:1h, trend:ETHUSDT:1h | trend:SOLUSDT:15m |" in rendered
    assert "## Trade Coverage" in rendered
    assert "| range | 1 | 37 | 0 | 37 | 0 | 63 |" in rendered
    assert "| trend | 5 | 72 | 4 | 5 | 86 | 28 |" in rendered
    assert "## Route Coverage" in rendered
    assert "| trend:ETHUSDT:1h | trend | fail | accumulate_oos | 5 | 25 | 95 |" in rendered
    assert "| trend:ADAUSDT:1h | trend | fail | accumulate_oos | 6 | 24 | 94 |" in rendered
    assert "| trend:BNBUSDT:1h | trend | fail | accumulate_oos | 7 | 23 | 93 |" in rendered
    assert "| trend:ADAUSDT:30m | trend | fail | accumulate_oos | 16 | 14 | 84 |" in rendered
    assert "| trend:SOLUSDT:15m | trend | fail | drop_or_retune | 38 | 0 | 62 |" in rendered
    assert "## Final Holdout Delta" in rendered
    assert "| range | 1 | 0.1000 | 2.0000 | 0.3000 | -0.0200 | 4.0000 |" in rendered
    assert "| trend | 5 | -0.2000 | -3.0000 | -0.4000 | 0.0500 | -1.0000 |" in rendered


def test_strategy_quality_report_renders_json_payload(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "weekly_revalidation_report.json"
    out_path = tmp_path / "strategy_quality_report.json"
    report_path.write_text(
        json.dumps(
            {
                "overview": {
                    "portfolio_status": "warn",
                    "strategy_quality_summary": {
                        "trend": {
                            "total": 1,
                            "sample_thin_count": 1,
                            "oos_quality_count": 0,
                            "recommendation": "accumulate_oos",
                        }
                    },
                    "portfolio_strategy_priority_summary": {
                        "trend": {
                            "recommendation": "bundle_review",
                            "priority_route_keys": ["trend:ETHUSDT:1h"],
                        }
                    },
                    "portfolio_next_action_summary": {
                        "trend": {
                            "selected_route_count": 1,
                            "qualified_route_count": 0,
                            "recommendation": "bundle_review",
                            "accumulate_oos_route_keys": ["trend:ETHUSDT:1h"],
                            "drop_or_retune_route_keys": [],
                        }
                    },
                },
                "selection_bias_audit": {
                    "final_holdout_summary": {
                        "strategy_summary": {
                            "trend": {
                                "route_count": 1,
                                "avg_delta_pf": 0.0,
                                "avg_delta_expectancy_bps": 0.0,
                                "avg_delta_period_pnl": 0.0,
                                "avg_delta_max_dd": 0.0,
                                "avg_delta_closed_trades": 0.0,
                            }
                        }
                    }
                },
                "route_quality_audit": {
                    "route_actions": [
                        {
                            "route_key": "trend:ETHUSDT:1h",
                            "strategy": "trend",
                            "recommendation": "accumulate_oos",
                        }
                    ]
                },
                "statistical_qualification": {
                    "routes": [
                        {
                            "route_key": "trend:ETHUSDT:1h",
                            "strategy": "trend",
                            "status": "fail",
                            "metrics": {"closed_trades": 0},
                        }
                    ]
                },
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    _run_script(
        repo_root,
        {
            "REPORT_PATH": str(report_path),
            "OUT_PATH": str(out_path),
        },
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["portfolio_status"] == "warn"
    assert payload["strategy_quality_summary"]["trend"]["recommendation"] == "accumulate_oos"
    assert payload["portfolio_strategy_priority_summary"]["trend"]["priority_route_keys"] == ["trend:ETHUSDT:1h"]
    assert payload["portfolio_next_action_summary"]["trend"]["accumulate_oos_route_keys"] == ["trend:ETHUSDT:1h"]
    assert payload["trade_coverage_summary"]["trend"]["closed_trades"] == 0
    assert payload["route_coverage_summary"][0]["recommendation"] == "accumulate_oos"
    assert payload["selection_bias_final_holdout_strategy_summary"]["trend"]["route_count"] == 1
