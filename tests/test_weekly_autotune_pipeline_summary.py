from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _run_pipeline(repo_root: Path, env: dict[str, str]) -> None:
    subprocess.run(
        ["bash", "scripts/weekly_autotune_pipeline.sh"],
        cwd=repo_root,
        env={**os.environ, **env},
        check=True,
        capture_output=True,
        text=True,
    )


def _write_minimal_weekly_fixtures(manifest_dir: Path, weekly_dir: Path) -> None:
    manifest = {
        "selection": {
            "timeframe": "15m",
            "trade_routes": [
                {
                    "symbol": "BNBUSDT",
                    "strategy": "trend",
                    "timeframe": "15m",
                    "expected_regime": "TREND",
                    "candidate_status": "core",
                    "statistical_status": "pass",
                    "selection_source": "autotune",
                },
                {
                    "symbol": "SOLUSDT",
                    "strategy": "range",
                    "timeframe": "15m",
                    "expected_regime": "RANGE",
                    "candidate_status": "core",
                    "statistical_status": "pass",
                    "selection_source": "autotune",
                },
            ],
        }
    }
    weekly_report = {
        "overview": {
            "portfolio_status": "pass",
            "portfolio_qualification_summary": {
                "status": "pass",
                "required_route_count": 2,
                "required_strategy_count": 2,
                "qualified_route_count": 2,
                "qualified_strategy_count": 2,
                "selected_route_keys": ["trend:BNBUSDT:15m", "range:SOLUSDT:15m"],
                "qualified_route_keys": ["trend:BNBUSDT:15m", "range:SOLUSDT:15m"],
                "selected_strategy_keys": ["trend", "range"],
                "qualified_strategy_keys": ["trend", "range"],
                "reasons": ["fixture"],
            },
            "portfolio_qualification_gap_summary": {
                "required_route_count": 2,
                "required_strategy_count": 2,
                "next_route_keys": ["trend:BNBUSDT:15m", "range:SOLUSDT:15m"],
            },
            "portfolio_next_action_summary": {
                "trend": {
                    "selected_route_count": 1,
                    "qualified_route_count": 1,
                    "recommendation": "monitor",
                    "sample_thin_count": 0,
                    "oos_quality_count": 1,
                    "accumulate_oos_route_keys": [],
                    "drop_or_retune_route_keys": [],
                },
                "range": {
                    "selected_route_count": 1,
                    "qualified_route_count": 1,
                    "recommendation": "monitor",
                    "sample_thin_count": 0,
                    "oos_quality_count": 1,
                    "accumulate_oos_route_keys": [],
                    "drop_or_retune_route_keys": [],
                },
            },
            "portfolio_next_action_route_keys": ["trend:BNBUSDT:15m", "range:SOLUSDT:15m"],
            "strategy_quality_summary": {
                "trend": {
                    "total": 1,
                    "sample_thin_count": 0,
                    "oos_quality_count": 1,
                    "recommendation": "monitor",
                },
                "range": {
                    "total": 1,
                    "sample_thin_count": 0,
                    "oos_quality_count": 1,
                    "recommendation": "monitor",
                },
            },
            "portfolio_strategy_priority_summary": {
                "trend": {
                    "recommendation": "monitor",
                    "priority_route_keys": ["trend:BNBUSDT:15m"],
                },
                "range": {
                    "recommendation": "monitor",
                    "priority_route_keys": ["range:SOLUSDT:15m"],
                },
            },
            "route_quality_audit": {
                "route_actions": [
                    {
                        "route_key": "trend:BNBUSDT:15m",
                        "recommendation": "monitor",
                    },
                    {
                        "route_key": "range:SOLUSDT:15m",
                        "recommendation": "monitor",
                    },
                ]
            },
            "selection_bias_final_holdout_strategy_summary": {
                "trend": {"status": "visible"},
                "range": {"status": "visible"},
            },
        },
        "statistical_qualification": {
            "status": "pass",
            "qualification_report_path": "qualification.json",
            "passed_route_keys": ["trend:BNBUSDT:15m", "range:SOLUSDT:15m"],
            "routes": [
                {
                    "route_key": "trend:BNBUSDT:15m",
                    "strategy": "trend",
                    "status": "pass",
                    "metrics": {"closed_trades": 40},
                },
                {
                    "route_key": "range:SOLUSDT:15m",
                    "strategy": "range",
                    "status": "pass",
                    "metrics": {"closed_trades": 42},
                },
            ],
        },
        "route_quality_audit": {
            "route_actions": [
                {
                    "route_key": "trend:BNBUSDT:15m",
                    "recommendation": "monitor",
                },
                {
                    "route_key": "range:SOLUSDT:15m",
                    "recommendation": "monitor",
                },
            ]
        },
        "selection_bias_audit": {
            "final_holdout_summary": {
                "strategy_summary": {
                    "trend": {"status": "visible"},
                    "range": {"status": "visible"},
                }
            }
        },
    }

    manifest_dir.mkdir(parents=True, exist_ok=True)
    weekly_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "route_selection_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    (weekly_dir / "weekly_revalidation_report.json").write_text(
        json.dumps(weekly_report, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def test_weekly_autotune_pipeline_summary_includes_strategy_reports(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    run_root = tmp_path / "weekly_autotune"
    manifest_dir = run_root / "manifest"
    weekly_dir = run_root / "weekly_revalidation"
    _write_minimal_weekly_fixtures(manifest_dir, weekly_dir)

    _run_pipeline(
        repo_root,
        {
            "RUN_ROOT": str(run_root),
            "RUN_EXPANSION": "0",
            "RUN_REFINEMENT": "0",
            "RUN_WEEKLY": "0",
        },
    )

    summary = json.loads((run_root / "pipeline_summary.json").read_text(encoding="utf-8"))
    assert summary["runtime"]["strategy_quality_report_path"] == str(weekly_dir / "strategy_quality_report.md")
    assert summary["runtime"]["strategy_quality_report_json_path"] == str(weekly_dir / "strategy_quality_report.json")
    assert summary["runtime"]["ai_strategy_progress_report_path"] == str(weekly_dir / "ai_strategy_progress_report.md")
    assert summary["runtime"]["ai_strategy_progress_report_json_path"] == str(weekly_dir / "ai_strategy_progress_report.json")
    assert summary["runtime_options"]["production"]["statistical_gate_mode"] == "hard"
    assert (weekly_dir / "strategy_quality_report.md").exists()
    assert (weekly_dir / "strategy_quality_report.json").exists()
    assert (weekly_dir / "ai_strategy_progress_report.md").exists()
    assert (weekly_dir / "ai_strategy_progress_report.json").exists()
