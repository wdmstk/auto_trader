from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _run_script(repo_root: Path, env: dict[str, str]) -> None:
    subprocess.run(
        ["bash", "scripts/ai_strategy_progress_report.sh"],
        cwd=repo_root,
        env={**os.environ, **env},
        check=True,
        capture_output=True,
        text=True,
    )


def test_ai_strategy_progress_report_renders_progress_table(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "weekly_revalidation_report.json"
    out_path = tmp_path / "ai_strategy_progress_report.md"
    report_path.write_text(
        json.dumps(
            {
                "overview": {
                    "portfolio_status": "fail",
                    "route_priority_summary": {
                        "priority_route_keys": [
                            "trend:ADAUSDT:1h",
                            "trend:ADAUSDT:30m",
                            "trend:BNBUSDT:1h",
                            "trend:ETHUSDT:1h",
                            "range:SOLUSDT:30m",
                            "trend:SOLUSDT:15m",
                        ]
                    },
                    "strategy_quality_summary": {
                        "range": {
                            "recommendation": "drop_or_retune",
                            "sample_thin_count": 0,
                            "oos_quality_count": 1,
                        },
                        "trend": {
                            "recommendation": "drop_or_retune",
                            "sample_thin_count": 4,
                            "oos_quality_count": 1,
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
                    "selection_bias_audit": {
                        "final_holdout_summary": {
                            "strategy_summary": {
                                "range": {"route_count": 1},
                                "trend": {"route_count": 5},
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
                        ]
                    },
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
                "portfolio_qualification": {
                    "status": "fail",
                    "selected_route_count": 6,
                    "qualified_route_count": 0,
                    "required_route_count": 2,
                    "missing_route_count": 6,
                    "selected_strategy_count": 2,
                    "qualified_strategy_count": 0,
                    "required_strategy_count": 2,
                    "missing_strategy_count": 2,
                    "selected_route_keys": [
                        "range:SOLUSDT:30m",
                        "trend:ADAUSDT:1h",
                        "trend:ADAUSDT:30m",
                        "trend:BNBUSDT:1h",
                        "trend:ETHUSDT:1h",
                        "trend:SOLUSDT:15m",
                    ],
                    "qualified_route_keys": [],
                    "selected_strategy_keys": ["range", "trend"],
                    "qualified_strategy_keys": [],
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
    assert "# AI-013-017 Progress Report" in rendered
    assert "| AI-013 | drop_or_retune | trend:SOLUSDT:15m は Production 候補から外す前提で扱う |" in rendered
    assert "| AI-016 | fail | portfolio-level pass には未到達 |" in rendered
    assert "strategy_quality_summary.trend.sample_thin_count=4" in rendered
    assert "| trend | bundle_review | trend:ADAUSDT:1h, trend:ADAUSDT:30m, trend:BNBUSDT:1h, trend:ETHUSDT:1h, trend:SOLUSDT:15m |" in rendered
    assert "| trend | 5 | 0 | bundle_review | trend:ADAUSDT:1h, trend:ADAUSDT:30m, trend:BNBUSDT:1h, trend:ETHUSDT:1h | trend:SOLUSDT:15m |" in rendered
    assert "## Pass Gaps" in rendered
    assert "- route_gap_to_pass: 2" in rendered
    assert "- strategy_gap_to_pass: 2" in rendered
    assert "- selected_route_count: 6" in rendered
    assert "- selected_strategy_count: 2" in rendered
    assert "## Trade Coverage" in rendered
    assert "| range | 1 | 37 | 0 | 37 | 0 | 63 |" in rendered
    assert "| trend | 5 | 72 | 4 | 5 | 86 | 28 |" in rendered
    assert "## Route Coverage" in rendered
    assert "| trend:ETHUSDT:1h | trend | fail | accumulate_oos | 5 | 25 | 95 |" in rendered
    assert "| trend:ADAUSDT:1h | trend | fail | accumulate_oos | 6 | 24 | 94 |" in rendered
    assert "| trend:BNBUSDT:1h | trend | fail | accumulate_oos | 7 | 23 | 93 |" in rendered
    assert "| trend:ADAUSDT:30m | trend | fail | accumulate_oos | 16 | 14 | 84 |" in rendered
    assert "| trend:SOLUSDT:15m | trend | fail | drop_or_retune | 38 | 0 | 62 |" in rendered
    assert "## Gate Split" in rendered
    assert "| soft | Testnet / analysis | statistical fail route を残して原因分析と運用検証に使う |" in rendered
    assert "| hard | Production / fail-closed | statistical pass route のみを本番候補に残す |" in rendered
    assert "## Final Holdout" in rendered


def test_ai_strategy_progress_report_renders_json_payload(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "weekly_revalidation_report.json"
    out_path = tmp_path / "ai_strategy_progress_report.json"
    report_path.write_text(
        json.dumps(
            {
                "overview": {"portfolio_status": "fail"},
                "portfolio_qualification": {"status": "fail"},
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
                            "metrics": {"closed_trades": 0},
                        }
                    ]
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
            },
            ensure_ascii=True,
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
    assert payload["portfolio_status"] == "fail"
    assert payload["entries"]["AI-013"]["status"] == "drop_or_retune"
    assert payload["entries"]["AI-016"]["status"] == "fail"
    assert payload["portfolio_strategy_priority_summary"] == {}
    assert payload["gate_split_summary"]["soft"]["purpose"] == "Testnet / analysis"
    assert payload["gate_split_summary"]["hard"]["current_role"] == "statistical pass route のみを本番候補に残す"
    assert payload["route_coverage_summary"][0]["recommendation"] == "accumulate_oos"
    assert payload["trade_coverage_summary"]["trend"]["closed_trades"] == 0
    assert payload["selection_bias_final_holdout_strategy_summary"]["trend"]["route_count"] == 1
