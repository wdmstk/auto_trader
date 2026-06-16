from __future__ import annotations

import json
import os
import shutil
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


def test_weekly_autotune_pipeline_summary_includes_strategy_reports(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    run_root = tmp_path / "weekly_autotune"
    manifest_dir = run_root / "manifest"
    weekly_dir = run_root / "weekly_revalidation"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    weekly_dir.mkdir(parents=True, exist_ok=True)

    src_manifest_dir = repo_root / "data/validation/weekly_autotune/manifest"
    src_weekly_dir = repo_root / "data/validation/weekly_autotune/weekly_revalidation"
    for name in ["route_selection_manifest.json", "route_selection_manifest.md"]:
        shutil.copy2(src_manifest_dir / name, manifest_dir / name)
    for name in [
        "weekly_revalidation_report.json",
        "manifest_vs_weekly_diff.json",
        "manifest_vs_weekly_diff.md",
    ]:
        shutil.copy2(src_weekly_dir / name, weekly_dir / name)

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
