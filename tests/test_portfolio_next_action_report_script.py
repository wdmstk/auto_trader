from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _run_script(repo_root: Path, env: dict[str, str]) -> None:
    subprocess.run(
        ["bash", "scripts/portfolio_next_action_report.sh"],
        cwd=repo_root,
        env={**os.environ, **env},
        check=True,
        capture_output=True,
        text=True,
    )


def test_portfolio_next_action_report_renders_route_coverage(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "weekly_revalidation_report.json"
    out_path = tmp_path / "portfolio_next_action_report.md"
    report_path.write_text(
        json.dumps(
            {
                "overview": {
                    "portfolio_status": "fail",
                    "portfolio_qualification_summary": {
                        "status": "fail",
                        "required_route_count": 2,
                        "required_strategy_count": 2,
                        "missing_route_count": 6,
                        "missing_strategy_count": 2,
                        "reasons": ["contains_non_qualified_routes"],
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
                    "portfolio_qualification_gap_summary": {
                        "required_route_count": 2,
                        "required_strategy_count": 2,
                        "next_route_keys": [
                            "trend:ADAUSDT:1h",
                            "trend:ADAUSDT:30m",
                            "trend:BNBUSDT:1h",
                            "trend:ETHUSDT:1h",
                            "range:SOLUSDT:30m",
                            "trend:SOLUSDT:15m",
                        ],
                    },
                    "portfolio_next_action_summary": {
                        "range": {
                            "selected_route_count": 1,
                            "qualified_route_count": 0,
                            "recommendation": "bundle_review",
                            "sample_thin_count": 0,
                            "oos_quality_count": 1,
                            "accumulate_oos_route_keys": [],
                            "drop_or_retune_route_keys": ["range:SOLUSDT:30m"],
                        },
                        "trend": {
                            "selected_route_count": 5,
                            "qualified_route_count": 0,
                            "recommendation": "bundle_review",
                            "sample_thin_count": 4,
                            "oos_quality_count": 1,
                            "accumulate_oos_route_keys": [
                                "trend:ADAUSDT:1h",
                                "trend:ADAUSDT:30m",
                                "trend:BNBUSDT:1h",
                                "trend:ETHUSDT:1h",
                            ],
                            "drop_or_retune_route_keys": ["trend:SOLUSDT:15m"],
                        },
                    },
                    "portfolio_next_action_route_keys": [
                        "trend:ADAUSDT:1h",
                        "trend:ADAUSDT:30m",
                        "trend:BNBUSDT:1h",
                        "trend:ETHUSDT:1h",
                        "range:SOLUSDT:30m",
                        "trend:SOLUSDT:15m",
                    ],
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
    assert "# Portfolio Next Action Report" in rendered
    assert "- next_route_keys: trend:ADAUSDT:1h, trend:ADAUSDT:30m, trend:BNBUSDT:1h, trend:ETHUSDT:1h, range:SOLUSDT:30m, trend:SOLUSDT:15m" in rendered
    assert "## Qualification" in rendered
    assert "- selected_route_keys: range:SOLUSDT:30m, trend:ADAUSDT:1h, trend:ADAUSDT:30m, trend:BNBUSDT:1h, trend:ETHUSDT:1h, trend:SOLUSDT:15m" in rendered
    assert "- qualified_route_keys: -" in rendered
    assert "- selected_strategy_keys: range, trend" in rendered
    assert "- qualified_strategy_keys: -" in rendered
    assert "- pass_path: need 2 qualified routes across 2 strategies" in rendered
    assert "## Pass Gaps" in rendered
    assert "- route_gap_to_pass: 2" in rendered
    assert "- strategy_gap_to_pass: 2" in rendered
    assert "- remaining_selected_routes: 6" in rendered
    assert "- remaining_selected_strategies: 2" in rendered
    assert "## Route Coverage" in rendered
    assert "| trend:ETHUSDT:1h | trend | fail | accumulate_oos | 5 | 25 | 95 |" in rendered
    assert "| trend:ADAUSDT:1h | trend | fail | accumulate_oos | 6 | 24 | 94 |" in rendered
    assert "| trend:BNBUSDT:1h | trend | fail | accumulate_oos | 7 | 23 | 93 |" in rendered
    assert "| trend:ADAUSDT:30m | trend | fail | accumulate_oos | 16 | 14 | 84 |" in rendered
    assert "| range:SOLUSDT:30m | range | fail | drop_or_retune | 37 | 0 | 63 |" in rendered
    assert "| trend:SOLUSDT:15m | trend | fail | drop_or_retune | 38 | 0 | 62 |" in rendered
