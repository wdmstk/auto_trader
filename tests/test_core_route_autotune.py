from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from _pytest.monkeypatch import MonkeyPatch


def _load_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "core_route_autotune.py"
    spec = importlib.util.spec_from_file_location("core_route_autotune", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_select_targets_expansion_excludes_baseline_core() -> None:
    module = _load_module()
    candidate_report = {
        "rows": [
            {
                "strategy": "trend",
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "candidate_status": "core",
                "closed_trades_mean": 12.0,
                "pf_mean": 1.5,
                "expectancy_bps_mean": 2.0,
                "period_pnl_mean": 3.0,
                "max_dd_mean": 0.04,
            },
            {
                "strategy": "range",
                "symbol": "ETHUSDT",
                "timeframe": "30m",
                "candidate_status": "probe",
                "closed_trades_mean": 15.0,
                "pf_mean": 1.1,
                "expectancy_bps_mean": 1.0,
                "period_pnl_mean": 1.0,
                "max_dd_mean": 0.03,
            },
        ]
    }

    targets = module.select_targets(candidate_report, 8, 4, "expansion")

    assert [route.key for route in targets] == ["range:ETHUSDT:30m"]


def test_select_targets_core_refinement_only_selects_baseline_core() -> None:
    module = _load_module()
    candidate_report = {
        "rows": [
            {
                "strategy": "trend",
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "candidate_status": "core",
                "closed_trades_mean": 12.0,
                "pf_mean": 1.5,
                "expectancy_bps_mean": 2.0,
                "period_pnl_mean": 3.0,
                "max_dd_mean": 0.04,
            },
            {
                "strategy": "range",
                "symbol": "ETHUSDT",
                "timeframe": "30m",
                "candidate_status": "probe",
                "closed_trades_mean": 15.0,
                "pf_mean": 1.1,
                "expectancy_bps_mean": 1.0,
                "period_pnl_mean": 1.0,
                "max_dd_mean": 0.03,
            },
        ]
    }

    targets = module.select_targets(candidate_report, 8, 4, "core_refinement")

    assert [route.key for route in targets] == ["trend:BTCUSDT:1h"]


def test_normalize_selection_mode_maps_refinement_aliases() -> None:
    module = _load_module()

    assert module.normalize_selection_mode("core_refinement") == "core_refinement"
    assert module.normalize_selection_mode("refine_core") == "core_refinement"
    assert module.normalize_selection_mode("refinement") == "core_refinement"
    assert module.normalize_selection_mode("anything_else") == "expansion"


def test_resolved_parallel_settings_prefers_simplified_env_names(
    monkeypatch: MonkeyPatch,
) -> None:
    module = _load_module()
    monkeypatch.setenv("STAGE_DATA_PARALLEL", "1")
    monkeypatch.setenv("STAGE_CASE_PARALLEL", "4")
    monkeypatch.delenv("HOLD_CASE_PARALLEL", raising=False)
    monkeypatch.delenv("REGIME_CASE_PARALLEL", raising=False)

    settings = module.resolved_parallel_settings()

    assert settings == {
        "stage_data_parallel": 1,
        "stage_case_parallel": 4,
        "hold_case_parallel": 4,
        "regime_case_parallel": 4,
    }


def test_build_stage_env_uses_baseline_data_root_and_simple_layout(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    module = _load_module()
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "data/validation/test_out/route/trend_ETHUSDT_15m/hold"
    baseline_candidate = root / "data/validation/test_out/baseline/candidate_report.json"
    baseline_summary = root / "data/validation/test_out/baseline/timeframe_comparison_summary.json"
    baseline_result = root / "data/validation/test_out/baseline/timeframe_comparison_result_list.md"
    baseline_data_root = root / "data/validation/test_out/baseline/run_data"
    monkeypatch.setenv("STAGE_DATA_PARALLEL", "1")
    monkeypatch.setenv("STAGE_CASE_PARALLEL", "4")

    env = module.build_stage_env(
        out_dir,
        baseline_candidate,
        baseline_summary,
        baseline_result,
        baseline_data_root,
    )

    assert env["BASE_DATA_ROOT"] == "data/validation/test_out/baseline/run_data"
    assert env["PARALLEL"] == "1"
    assert env["CASE_PARALLEL"] == "4"
    assert env["OUTPUT_LAYOUT"] == "simple_stage"
