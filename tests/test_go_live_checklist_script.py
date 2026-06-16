from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _base_checklist() -> str:
    return """# Checklist

- [ ] 8時間以上の連続運転証跡
- [ ] Runtime Metrics 自動採点レポートを取得
- [ ] Longrun record へサマリ追記
- [ ] .lock 長時間残留なし
- [ ] updated_at 更新継続
- [ ] watcher 生存継続
- [ ] Go-Live Ready（通知保留条件付き）
- 判定者: pending
- 判定日: pending

<!-- AUTO_DECISION_NOTES_START -->
old
<!-- AUTO_DECISION_NOTES_END -->

<!-- AUTO_OPEN_ITEMS_START -->
old
<!-- AUTO_OPEN_ITEMS_END -->
"""


def _run_script(repo_root: Path, env: dict[str, str]) -> dict[str, object]:
    proc = subprocess.run(
        ["bash", "scripts/update_go_live_checklist.sh"],
        cwd=repo_root,
        env={**os.environ, **env},
        check=True,
        capture_output=True,
        text=True,
    )
    return cast(dict[str, object], json.loads(proc.stdout.strip().splitlines()[-1]))


def test_update_go_live_checklist_prefers_runtime_env_weekly_report(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    checklist = tmp_path / "trading-go-live-checklist.md"
    checkpoints = tmp_path / "longrun_checkpoints.jsonl"
    health = tmp_path / "runtime_metrics_health_report.json"
    runtime_env = tmp_path / "route_selection_runtime.env"
    pipeline_summary = tmp_path / "pipeline_summary.json"
    weekly_canonical = tmp_path / "weekly_autotune/weekly_revalidation/weekly_revalidation_report.json"
    weekly_legacy = tmp_path / "weekly_revalidation/weekly_revalidation_report.json"
    statistical = tmp_path / "statistical/qualification_report.json"
    strategy_json = tmp_path / "weekly_autotune/weekly_revalidation/strategy_quality_report.json"
    ai_progress_json = tmp_path / "weekly_autotune/weekly_revalidation/ai_strategy_progress_report.json"

    checklist.write_text(_base_checklist(), encoding="utf-8")
    checkpoints.write_text(
        json.dumps({"runtime_alive": True, "runtime_updated_progress": True}, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    recent = datetime.now(UTC).isoformat()
    _write(
        health,
        {
            "overall_status": "pass",
            "generated_at": recent,
            "input_path": "runtime_metrics.jsonl",
        },
    )
    _write(
        statistical,
        {
            "status": "fail",
            "run_id": "run-abc",
            "generated_at": recent,
            "routes": [{"route_key": "trend:SOLUSDT:15m", "status": "fail"}],
        },
    )
    _write(
        weekly_canonical,
        {
            "status": "warn",
            "run_id": "run-abc",
            "generated_at": recent,
            "statistical_qualification": {
                "status": "fail",
                "qualification_report_path": str(statistical),
            },
        },
    )
    _write(
        strategy_json,
        {
            "generated_at": recent,
            "portfolio_status": "fail",
            "strategy_quality_summary": {
                "range": {"recommendation": "drop_or_retune"},
                "trend": {"recommendation": "drop_or_retune"},
            },
        },
    )
    _write(
        ai_progress_json,
        {
            "generated_at": recent,
            "portfolio_status": "fail",
            "entries": {
                "AI-013": {"status": "drop_or_retune"},
                "AI-014": {"status": "drop_or_retune"},
                "AI-015": {"status": "sample_thin"},
                "AI-016": {"status": "fail"},
                "AI-017": {"status": "visible"},
            },
        },
    )
    _write(
        weekly_legacy,
        {
            "status": "pass",
            "run_id": "legacy-run",
            "generated_at": recent,
            "statistical_qualification": {"status": "pass"},
        },
    )
    runtime_env.write_text(
        f"WEEKLY_REVALIDATION_REPORT_PATH={weekly_canonical}\nROUTE_SELECTION_PATH={weekly_canonical}\n",
        encoding="utf-8",
    )
    _write(
        pipeline_summary,
        {
            "runtime": {
                "weekly_report_path": str(weekly_canonical),
                "route_selection_path": str(weekly_canonical),
            }
        },
    )

    summary = _run_script(
        repo_root,
        {
            "CHECKLIST_PATH": str(checklist),
            "CHECKPOINTS_PATH": str(checkpoints),
            "HEALTH_REPORT_PATH": str(health),
            "RUNTIME_ENV_PATH": str(runtime_env),
            "PIPELINE_SUMMARY_PATH": str(pipeline_summary),
            "STRATEGY_REPORT_PATH": str(strategy_json.with_suffix(".md")),
            "STRATEGY_REPORT_JSON_PATH": str(strategy_json),
            "AI_PROGRESS_REPORT_PATH": str(ai_progress_json),
            "DRY_RUN": "true",
        },
    )

    assert summary["weekly_status"] == "warn"
    assert summary["statistical_status"] == "fail"
    assert summary["weekly_report_path"] == str(weekly_canonical)
    assert summary["weekly_report_path_source"] == "runtime_env:WEEKLY_REVALIDATION_REPORT_PATH"
    assert summary["go_live_ready"] is False


def test_update_go_live_checklist_reads_strategy_quality_report(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    checklist = tmp_path / "trading-go-live-checklist.md"
    checkpoints = tmp_path / "longrun_checkpoints.jsonl"
    health = tmp_path / "runtime_metrics_health_report.json"
    runtime_env = tmp_path / "route_selection_runtime.env"
    pipeline_summary = tmp_path / "pipeline_summary.json"
    weekly = tmp_path / "weekly_autotune/weekly_revalidation/weekly_revalidation_report.json"
    statistical = tmp_path / "statistical/qualification_report.json"
    strategy = tmp_path / "weekly_autotune/weekly_revalidation/strategy_quality_report.md"
    strategy_json = tmp_path / "weekly_autotune/weekly_revalidation/strategy_quality_report.json"
    ai_progress_json = tmp_path / "weekly_autotune/weekly_revalidation/ai_strategy_progress_report.json"

    checklist.write_text(_base_checklist(), encoding="utf-8")
    checkpoints.write_text(
        json.dumps({"runtime_alive": True, "runtime_updated_progress": True}, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    recent = datetime.now(UTC).isoformat()
    _write(health, {"overall_status": "pass", "generated_at": recent})
    _write(statistical, {"status": "fail", "generated_at": recent, "routes": []})
    _write(
        weekly,
        {
            "status": "warn",
            "run_id": "run-abc",
            "generated_at": recent,
            "overview": {
                "strategy_quality_summary": {
                    "range": {"recommendation": "drop_or_retune"},
                    "trend": {"recommendation": "accumulate_oos"},
                }
            },
            "statistical_qualification": {
                "status": "fail",
                "qualification_report_path": str(statistical),
            },
        },
    )
    _write(strategy, "# Strategy Quality Report\n")
    _write(strategy_json, {"generated_at": recent, "portfolio_status": "warn"})
    _write(ai_progress_json, {"generated_at": recent, "portfolio_status": "warn"})
    runtime_env.write_text(f"WEEKLY_REVALIDATION_REPORT_PATH={weekly}\n", encoding="utf-8")
    _write(pipeline_summary, {"runtime": {"weekly_report_path": str(weekly)}})

    summary = _run_script(
        repo_root,
        {
            "CHECKLIST_PATH": str(checklist),
            "CHECKPOINTS_PATH": str(checkpoints),
            "HEALTH_REPORT_PATH": str(health),
            "RUNTIME_ENV_PATH": str(runtime_env),
            "PIPELINE_SUMMARY_PATH": str(pipeline_summary),
            "STRATEGY_REPORT_PATH": str(strategy),
            "STRATEGY_REPORT_JSON_PATH": str(strategy_json),
            "AI_PROGRESS_REPORT_PATH": str(ai_progress_json),
            "DRY_RUN": "true",
        },
    )

    assert summary["strategy_report_path"] == str(strategy)
    assert summary["strategy_report_json_path"] == str(strategy_json)
    assert summary["ai_progress_report_path"] == str(ai_progress_json)
    assert summary["strategy_quality_range_recommendation"] == "drop_or_retune"
    assert summary["strategy_quality_trend_recommendation"] == "accumulate_oos"
    assert summary["go_live_ready"] is False


def test_update_go_live_checklist_rejects_stale_artifacts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    checklist = tmp_path / "trading-go-live-checklist.md"
    checkpoints = tmp_path / "longrun_checkpoints.jsonl"
    health = tmp_path / "runtime_metrics_health_report.json"
    weekly = tmp_path / "weekly_autotune/weekly_revalidation/weekly_revalidation_report.json"
    statistical = tmp_path / "statistical/qualification_report.json"
    runtime_env = tmp_path / "route_selection_runtime.env"
    pipeline_summary = tmp_path / "pipeline_summary.json"
    ai_progress_json = tmp_path / "weekly_autotune/weekly_revalidation/ai_strategy_progress_report.json"

    checklist.write_text(_base_checklist(), encoding="utf-8")
    checkpoints.write_text(
        json.dumps({"runtime_alive": True, "runtime_updated_progress": True}, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    old = (datetime.now(UTC) - timedelta(hours=72)).isoformat()
    _write(health, {"overall_status": "pass", "generated_at": old})
    _write(
        statistical,
        {
            "status": "pass",
            "run_id": "run-stale",
            "generated_at": old,
            "routes": [],
        },
    )
    _write(
        weekly,
        {
            "status": "pass",
            "run_id": "run-stale",
            "generated_at": old,
            "statistical_qualification": {
                "status": "pass",
                "qualification_report_path": str(statistical),
            },
        },
    )
    runtime_env.write_text(
        f"WEEKLY_REVALIDATION_REPORT_PATH={weekly}\n",
        encoding="utf-8",
    )
    _write(ai_progress_json, {"generated_at": old, "portfolio_status": "pass"})
    _write(
        pipeline_summary,
        {"runtime": {"weekly_report_path": str(weekly)}},
    )

    summary = _run_script(
        repo_root,
        {
            "CHECKLIST_PATH": str(checklist),
            "CHECKPOINTS_PATH": str(checkpoints),
            "HEALTH_REPORT_PATH": str(health),
            "RUNTIME_ENV_PATH": str(runtime_env),
            "PIPELINE_SUMMARY_PATH": str(pipeline_summary),
            "MAX_ARTIFACT_AGE_HOURS": "24",
            "DRY_RUN": "true",
        },
    )

    assert summary["health_stale"] is True
    assert summary["weekly_stale"] is True
    assert summary["statistical_stale"] is True
    assert summary["go_live_ready"] is False
    reasons = cast(list[str], summary["unmet_reasons"])
    assert "runtime metrics health report が stale（No-Go）" in reasons
    assert "weekly strategy revalidation report が stale（No-Go）" in reasons
    assert "statistical qualification report が stale（No-Go）" in reasons
