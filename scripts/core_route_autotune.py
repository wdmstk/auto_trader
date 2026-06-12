#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = ROOT_DIR / "data/validation/core_route_autotune"


@dataclass
class Route:
    strategy: str
    symbol: str
    timeframe: str

    @property
    def key(self) -> str:
        return f"{self.strategy}:{self.symbol}:{self.timeframe}"

    @property
    def safe_key(self) -> str:
        return f"{self.strategy}_{self.symbol}_{self.timeframe}".replace(":", "_")


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, str(default)).strip()
    return int(value) if value else default


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


def safe_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def core_check_count(row: dict[str, Any]) -> int:
    checks = [
        safe_float(row.get("pf_mean", 0.0)) >= 1.2,
        safe_float(row.get("expectancy_bps_mean", 0.0)) > 0.0,
        safe_float(row.get("period_pnl_mean", 0.0)) > 0.0,
        safe_float(row.get("max_dd_mean", 0.0)) <= 0.08,
    ]
    return sum(1 for item in checks if item)


def candidate_rank(status: str) -> int:
    return {"core": 2, "probe": 1, "watchlist": 0}.get(status, -1)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], payload if isinstance(payload, dict) else {})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def parse_route(text: str) -> Route:
    strategy, symbol, timeframe = (part.strip() for part in text.split(":"))
    return Route(strategy=strategy, symbol=symbol, timeframe=timeframe)


def run_tuning(env_updates: dict[str, str], label: str) -> None:
    env = os.environ.copy()
    env.update(env_updates)
    print(f"[autotune] start {label}", flush=True)
    subprocess.run(
        ["./scripts/core_expansion_tuning.sh"],
        cwd=ROOT_DIR,
        env=env,
        check=True,
    )
    print(f"[autotune] done {label}", flush=True)


def normalize_selection_mode(value: str) -> str:
    mode = value.strip().lower()
    if mode in {"core_refinement", "refine_core", "refinement"}:
        return "core_refinement"
    return "expansion"


def select_targets(
    candidate_report: dict[str, Any],
    target_limit: int,
    max_watchlist: int,
    selection_mode: str,
) -> list[Route]:
    rows = [row for row in candidate_report.get("rows", []) if isinstance(row, dict)]
    mode = normalize_selection_mode(selection_mode)
    selected: list[dict[str, Any]] = []
    watchlist_count = 0
    for row in sorted(
        rows,
        key=lambda row: (
            -candidate_rank(str(row.get("candidate_status", ""))),
            -core_check_count(row),
            -safe_float(row.get("pf_mean", 0.0)),
            -safe_float(row.get("expectancy_bps_mean", 0.0)),
            -safe_float(row.get("period_pnl_mean", 0.0)),
            safe_float(row.get("max_dd_mean", 0.0)),
            -safe_float(row.get("closed_trades_mean", 0.0)),
            str(row.get("strategy", "")),
            str(row.get("symbol", "")),
            str(row.get("timeframe", "")),
        ),
    ):
        status = str(row.get("candidate_status", ""))
        trades = safe_float(row.get("closed_trades_mean", 0.0))
        pf = safe_float(row.get("pf_mean", 0.0))
        exp = safe_float(row.get("expectancy_bps_mean", 0.0))
        pnl = safe_float(row.get("period_pnl_mean", 0.0))
        dd = safe_float(row.get("max_dd_mean", 0.0))
        if trades <= 0:
            continue
        if mode == "core_refinement":
            if status == "core":
                selected.append(row)
            continue
        if status == "core":
            continue
        if status == "probe":
            selected.append(row)
            continue
        if dd > 0.15:
            continue
        if pf >= 1.0 or exp > -10.0 or pnl > 0.0:
            if watchlist_count < max_watchlist:
                selected.append(row)
                watchlist_count += 1
    return [
        Route(
            strategy=str(row["strategy"]),
            symbol=str(row["symbol"]),
            timeframe=str(row["timeframe"]),
        )
        for row in selected[:target_limit]
    ]


def pick_best_from_route_results(summary_path: Path, route_key: str) -> dict[str, Any] | None:
    if not summary_path.exists():
        return None
    payload = load_json(summary_path)
    route_results = payload.get("route_results", {})
    if not isinstance(route_results, dict):
        return None
    rows = route_results.get(route_key, [])
    if not isinstance(rows, list) or not rows:
        return None
    best = rows[0]
    return best if isinstance(best, dict) else None


def extract_hold_bars(config_label: str, strategy: str) -> int:
    prefix = "trend_hold" if strategy == "trend" else "range_hold"
    if not config_label.startswith(prefix):
        return 0
    value = config_label.removeprefix(prefix)
    return int(value) if value.isdigit() else 0


def should_run_regime(
    route: Route,
    diagnostics_path: Path,
    min_ratio: float,
) -> bool:
    if route.strategy != "trend" or not diagnostics_path.exists():
        return False
    payload = load_json(diagnostics_path)
    rows = payload.get("routes", [])
    for row in rows:
        if not isinstance(row, dict) or str(row.get("route", "")) != route.key:
            continue
        mask = safe_float(row.get("regime_trend_mask_rows", 0.0))
        blocked = safe_float(row.get("trend_mask_not_adopted_rows", 0.0))
        if mask <= 0:
            return False
        return (blocked / mask) >= min_ratio
    return False


def better_row(current: dict[str, Any] | None, candidate: dict[str, Any] | None) -> bool:
    if candidate is None:
        return False
    if current is None:
        return True
    current_key = (
        candidate_rank(str(current.get("candidate_status", ""))),
        core_check_count(current),
        1 if safe_float(current.get("closed_trades_mean", 0.0)) >= 10.0 else 0,
        safe_float(current.get("pf_mean", 0.0)),
        safe_float(current.get("expectancy_bps_mean", 0.0)),
        safe_float(current.get("period_pnl_mean", 0.0)),
        -safe_float(current.get("max_dd_mean", 0.0)),
    )
    candidate_key = (
        candidate_rank(str(candidate.get("candidate_status", ""))),
        core_check_count(candidate),
        1 if safe_float(candidate.get("closed_trades_mean", 0.0)) >= 10.0 else 0,
        safe_float(candidate.get("pf_mean", 0.0)),
        safe_float(candidate.get("expectancy_bps_mean", 0.0)),
        safe_float(candidate.get("period_pnl_mean", 0.0)),
        -safe_float(candidate.get("max_dd_mean", 0.0)),
    )
    return candidate_key > current_key


def stage_flags() -> dict[str, str]:
    return {
        "RUN_BASELINE": "0",
        "RUN_RANGE_MATRIX": "0",
        "RUN_TREND_MATRIX": "0",
        "RUN_TREND_NEXT_STEP_MATRIX": "0",
        "RUN_TREND_PROVISIONAL_CORE_MATRIX": "0",
        "RUN_TREND_ENTRY_THRESHOLD_MATRIX": "0",
        "RUN_HOLD_EXIT_MATRIX": "0",
        "RUN_REGIME_THRESHOLD_MATRIX": "0",
        "RUN_TREND_ENTRY_DIAGNOSTICS": "0",
        "RUN_FOLD_BREAKDOWN": "0",
        "RUN_LOSS_FOLD_REVIEW": "0",
        "RUN_LOSS_FOLD_TRADE_DETAIL": "0",
        "RUN_LOSS_HOLD_THRESHOLD": "0",
        "RUN_BUILD_AGGREGATE_REPORT": "0",
        "RUN_BUILD_TREND_NEXT_STEP_REPORT": "0",
        "RUN_BUILD_TREND_PROVISIONAL_CORE_REPORT": "0",
        "RUN_BUILD_TREND_ENTRY_THRESHOLD_REPORT": "0",
        "RUN_BUILD_HOLD_EXIT_REPORT": "0",
        "RUN_BUILD_REGIME_THRESHOLD_REPORT": "0",
    }


def resolved_parallel_settings() -> dict[str, int]:
    stage_data_parallel = env_int(
        "STAGE_DATA_PARALLEL",
        env_int("AUTOTUNE_PARALLEL", env_int("PARALLEL", 1)),
    )
    stage_case_parallel = env_int(
        "STAGE_CASE_PARALLEL",
        env_int("AUTOTUNE_CASE_PARALLEL", env_int("CASE_PARALLEL", 4)),
    )
    hold_case_parallel = env_int("HOLD_CASE_PARALLEL", stage_case_parallel)
    regime_case_parallel = env_int("REGIME_CASE_PARALLEL", stage_case_parallel)
    return {
        "stage_data_parallel": stage_data_parallel,
        "stage_case_parallel": stage_case_parallel,
        "hold_case_parallel": hold_case_parallel,
        "regime_case_parallel": regime_case_parallel,
    }


def build_stage_env(
    out_dir: Path,
    baseline_candidate_report_path: Path,
    baseline_summary_path: Path,
    baseline_result_list_path: Path,
    baseline_data_root: Path,
) -> dict[str, str]:
    parallel = resolved_parallel_settings()
    env = stage_flags()
    env.update(
        {
            "OUT_DIR": str(out_dir.relative_to(ROOT_DIR)),
            "BASELINE_CANDIDATE_REPORT_PATH": str(
                baseline_candidate_report_path.relative_to(ROOT_DIR)
            ),
            "BASELINE_SUMMARY_PATH": str(baseline_summary_path.relative_to(ROOT_DIR)),
            "BASELINE_RESULT_LIST_PATH": str(baseline_result_list_path.relative_to(ROOT_DIR)),
            "BASE_DATA_ROOT": str(baseline_data_root.relative_to(ROOT_DIR)),
            "PARALLEL": str(parallel["stage_data_parallel"]),
            "CASE_PARALLEL": str(parallel["stage_case_parallel"]),
            "HOLD_CASE_PARALLEL": str(parallel["hold_case_parallel"]),
            "REGIME_CASE_PARALLEL": str(parallel["regime_case_parallel"]),
            "OUTPUT_LAYOUT": "simple_stage",
        }
    )
    return env


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT_DIR))


def route_metrics(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "candidate_status": str(row.get("candidate_status", "")),
        "config_label": str(row.get("config_label", "baseline")),
        "pf_mean": safe_float(row.get("pf_mean", 0.0)),
        "expectancy_bps_mean": safe_float(row.get("expectancy_bps_mean", 0.0)),
        "period_pnl_mean": safe_float(row.get("period_pnl_mean", 0.0)),
        "max_dd_mean": safe_float(row.get("max_dd_mean", 0.0)),
        "closed_trades_mean": safe_float(row.get("closed_trades_mean", 0.0)),
        "core_check_count": core_check_count(row),
    }


def process_route(
    route: Route,
    route_runs_dir: Path,
    baseline_candidate_report_path: Path,
    baseline_summary_path: Path,
    baseline_result_list_path: Path,
    baseline_data_root: Path,
    base_row: dict[str, Any],
    provisional_core_min_trades: int,
    stop_on_confirmed_core: bool,
    auto_run_regime: bool,
    regime_block_ratio: float,
    selection_mode: str,
) -> dict[str, Any]:
    route_dir = route_runs_dir / route.safe_key
    route_dir.mkdir(parents=True, exist_ok=True)
    stage_results: list[dict[str, Any]] = []
    best_row: dict[str, Any] | None = dict(base_row)
    best_stage = "baseline"
    best_hold_bars = 0
    refinement_mode = (
        normalize_selection_mode(selection_mode) == "core_refinement"
        and str(base_row.get("candidate_status", "")) == "core"
    )

    hold_dir = route_dir / "hold"
    hold_env = build_stage_env(
        hold_dir,
        baseline_candidate_report_path,
        baseline_summary_path,
        baseline_result_list_path,
        baseline_data_root,
    )
    hold_env.update(
        {
            "RUN_HOLD_EXIT_MATRIX": "1",
            "RUN_BUILD_HOLD_EXIT_REPORT": "1",
            "HOLD_EXIT_ROUTES": route.key,
            "LOSS_HOLD_THRESHOLD_MAX_ROUTES": "3",
        }
    )
    if route.strategy == "trend":
        hold_env.update(
            {
                "RANGE_MAX_HOLD_BARS_LIST": "",
                "HOLD_EXIT_RANGE_SYMBOLS": "",
                "HOLD_EXIT_RANGE_TIMEFRAMES": "",
                "HOLD_EXIT_TREND_SYMBOLS": route.symbol,
                "HOLD_EXIT_TREND_TIMEFRAMES": route.timeframe,
            }
        )
    else:
        hold_env.update(
            {
                "TREND_MAX_HOLD_BARS_LIST": "",
                "HOLD_EXIT_TREND_SYMBOLS": "",
                "HOLD_EXIT_TREND_TIMEFRAMES": "",
                "HOLD_EXIT_RANGE_SYMBOLS": route.symbol,
                "HOLD_EXIT_RANGE_TIMEFRAMES": route.timeframe,
            }
        )
    run_tuning(hold_env, f"{route.key} hold")
    hold_summary_path = hold_dir / "hold_exit_summary.json"
    hold_best = pick_best_from_route_results(hold_summary_path, route.key)
    if hold_best:
        stage_results.append(
            {
                "stage": "hold",
                "summary_path": relative(hold_summary_path),
                "best": route_metrics(hold_best),
            }
        )
        if better_row(best_row, hold_best):
            best_row = hold_best
            best_stage = "hold"
        best_hold_bars = extract_hold_bars(str(hold_best.get("config_label", "")), route.strategy)

    confirmed = (
        best_row is not None
        and str(best_row.get("candidate_status", "")) == "core"
        and safe_float(best_row.get("closed_trades_mean", 0.0)) >= provisional_core_min_trades
    )
    if confirmed and stop_on_confirmed_core and not refinement_mode:
        return {
            "route": route.key,
            "baseline": route_metrics(base_row),
            "stages": stage_results,
            "selected_stage": best_stage,
            "selected": route_metrics(best_row),
            "final_state": "core_confirmed",
            "next_action": "ready_for_statistical_qualification",
        }

    if route.strategy == "range":
        range_dir = route_dir / "range_matrix"
        range_env = build_stage_env(
            range_dir,
            baseline_candidate_report_path,
            baseline_summary_path,
            baseline_result_list_path,
            baseline_data_root,
        )
        range_env.update(
            {
                "RUN_RANGE_MATRIX": "1",
                "RUN_BUILD_AGGREGATE_REPORT": "1",
                "CORE_CANDIDATE_ROUTES": route.key,
                "RANGE_TARGET_SYMBOLS": route.symbol,
                "RANGE_TARGET_TIMEFRAME": route.timeframe,
                "RANGE_MAX_HOLD_BARS": str(best_hold_bars),
            }
        )
        run_tuning(range_env, f"{route.key} range-matrix")
        range_summary_path = range_dir / "core_expansion_tuning_summary.json"
        range_best = pick_best_from_route_results(range_summary_path, route.key)
        if range_best:
            stage_results.append(
                {
                    "stage": "range_matrix",
                    "summary_path": relative(range_summary_path),
                    "best": route_metrics(range_best),
                }
            )
            if better_row(best_row, range_best):
                best_row = range_best
                best_stage = "range_matrix"
    else:
        trend_next_dir = route_dir / "trend_next_step"
        trend_next_env = build_stage_env(
            trend_next_dir,
            baseline_candidate_report_path,
            baseline_summary_path,
            baseline_result_list_path,
            baseline_data_root,
        )
        trend_next_env.update(
            {
                "RUN_TREND_NEXT_STEP_MATRIX": "1",
                "RUN_BUILD_TREND_NEXT_STEP_REPORT": "1",
                "TREND_NEXT_STEP_SYMBOLS": route.symbol,
                "TREND_NEXT_STEP_TIMEFRAMES": route.timeframe,
                "TREND_NEXT_STEP_ROUTES": route.key,
                "TREND_MAX_HOLD_BARS": str(best_hold_bars),
            }
        )
        run_tuning(trend_next_env, f"{route.key} trend-next")
        trend_next_summary_path = trend_next_dir / "trend_next_step_summary.json"
        trend_next_best = pick_best_from_route_results(trend_next_summary_path, route.key)
        if trend_next_best:
            stage_results.append(
                {
                    "stage": "trend_next_step",
                    "summary_path": relative(trend_next_summary_path),
                    "best": route_metrics(trend_next_best),
                }
            )
            if better_row(best_row, trend_next_best):
                best_row = trend_next_best
                best_stage = "trend_next_step"

        confirmed = (
            best_row is not None
            and str(best_row.get("candidate_status", "")) == "core"
            and safe_float(best_row.get("closed_trades_mean", 0.0)) >= provisional_core_min_trades
        )
        if not (confirmed and stop_on_confirmed_core and not refinement_mode):
            trend_entry_dir = route_dir / "trend_entry_threshold"
            trend_entry_env = build_stage_env(
                trend_entry_dir,
                baseline_candidate_report_path,
                baseline_summary_path,
                baseline_result_list_path,
                baseline_data_root,
            )
            trend_entry_env.update(
                {
                    "RUN_TREND_ENTRY_THRESHOLD_MATRIX": "1",
                    "RUN_BUILD_TREND_ENTRY_THRESHOLD_REPORT": "1",
                    "TREND_ENTRY_THRESHOLD_SYMBOLS": route.symbol,
                    "TREND_ENTRY_THRESHOLD_TIMEFRAMES": route.timeframe,
                    "TREND_ENTRY_THRESHOLD_ROUTES": route.key,
                    "TREND_MAX_HOLD_BARS": str(best_hold_bars),
                }
            )
            run_tuning(trend_entry_env, f"{route.key} trend-entry")
            trend_entry_summary_path = trend_entry_dir / "trend_entry_threshold_summary.json"
            trend_entry_best = pick_best_from_route_results(trend_entry_summary_path, route.key)
            if trend_entry_best:
                stage_results.append(
                    {
                        "stage": "trend_entry_threshold",
                        "summary_path": relative(trend_entry_summary_path),
                        "best": route_metrics(trend_entry_best),
                    }
                )
                if better_row(best_row, trend_entry_best):
                    best_row = trend_entry_best
                    best_stage = "trend_entry_threshold"

        confirmed = (
            best_row is not None
            and str(best_row.get("candidate_status", "")) == "core"
            and safe_float(best_row.get("closed_trades_mean", 0.0)) >= provisional_core_min_trades
        )
        baseline_regime_diag = route_dir / "baseline_regime_entry_diagnostics.json"
        if auto_run_regime:
            subprocess.run(
                [
                    "./scripts/regime_entry_diagnostics_report.sh",
                ],
                cwd=ROOT_DIR,
                env={
                    **os.environ.copy(),
                    "DATA_ROOT": relative(baseline_data_root),
                    "ROUTES": route.key,
                    "OUT_PATH": relative(route_dir / "baseline_regime_entry_diagnostics.md"),
                    "JSON_OUT": relative(baseline_regime_diag),
                },
                check=True,
            )
        if (
            auto_run_regime
            and not (confirmed and stop_on_confirmed_core and not refinement_mode)
            and should_run_regime(route, baseline_regime_diag, regime_block_ratio)
        ):
            regime_dir = route_dir / "regime"
            regime_env = build_stage_env(
                regime_dir,
                baseline_candidate_report_path,
                baseline_summary_path,
                baseline_result_list_path,
                baseline_data_root,
            )
            regime_env.update(
                {
                    "RUN_REGIME_THRESHOLD_MATRIX": "1",
                    "RUN_BUILD_REGIME_THRESHOLD_REPORT": "1",
                    "REGIME_THRESHOLD_ROUTES": route.key,
                    "REGIME_THRESHOLD_SYMBOLS": route.symbol,
                    "REGIME_THRESHOLD_TIMEFRAMES": route.timeframe,
                    "TREND_MAX_HOLD_BARS": str(best_hold_bars),
                }
            )
            run_tuning(regime_env, f"{route.key} regime")
            regime_summary_path = regime_dir / "regime_threshold_summary.json"
            regime_best = pick_best_from_route_results(regime_summary_path, route.key)
            if regime_best:
                stage_results.append(
                    {
                        "stage": "regime_threshold",
                        "summary_path": relative(regime_summary_path),
                        "best": route_metrics(regime_best),
                    }
                )
                if better_row(best_row, regime_best):
                    best_row = regime_best
                    best_stage = "regime_threshold"

    final_status = str(best_row.get("candidate_status", "")) if best_row else "unknown"
    final_trades = safe_float(best_row.get("closed_trades_mean", 0.0)) if best_row else 0.0
    if final_status == "core" and final_trades >= provisional_core_min_trades:
        final_state = "core_confirmed"
        next_action = "ready_for_statistical_qualification"
    elif final_status == "core":
        final_state = "core_provisional"
        next_action = "collect_more_trades_before_promotion"
    else:
        final_state = "no_core_found"
        next_action = "keep_watchlist_or_manual_logic_review"

    return {
        "route": route.key,
        "baseline": route_metrics(base_row),
        "stages": stage_results,
        "selected_stage": best_stage,
        "selected": route_metrics(best_row),
        "final_state": final_state,
        "next_action": next_action,
    }


def main() -> int:
    out_dir = Path(os.environ.get("OUT_DIR", str(DEFAULT_OUT_DIR)))
    if not out_dir.is_absolute():
        out_dir = ROOT_DIR / out_dir
    target_route_limit = env_int("TARGET_ROUTE_LIMIT", 8)
    max_watchlist_targets = env_int("MAX_WATCHLIST_TARGETS", 4)
    provisional_core_min_trades = env_int("PROVISIONAL_CORE_MIN_TRADES", 10)
    stop_on_confirmed_core = env_bool("STOP_ON_CONFIRMED_CORE", True)
    auto_run_regime = env_bool("AUTO_RUN_REGIME", True)
    regime_block_ratio = float(os.environ.get("REGIME_BLOCK_RATIO", "0.40"))
    route_parallel = env_int("ROUTE_PARALLEL", 2)
    parallel_settings = resolved_parallel_settings()
    selection_mode = normalize_selection_mode(os.environ.get("TARGET_SELECTION_MODE", "expansion"))

    out_dir.mkdir(parents=True, exist_ok=True)
    route_runs_dir = out_dir / "routes"
    route_runs_dir.mkdir(parents=True, exist_ok=True)

    baseline_env = stage_flags()
    baseline_env.update(
        {
            "OUT_DIR": relative(out_dir),
            "RUN_BASELINE": "1",
        }
    )
    run_tuning(baseline_env, "baseline")

    baseline_dir = out_dir / "baseline_all_symbols"
    baseline_candidate_report_path = baseline_dir / "candidate_report.json"
    baseline_summary_path = baseline_dir / "timeframe_comparison_summary.json"
    baseline_result_list_path = baseline_dir / "timeframe_comparison_result_list.md"
    baseline_data_root = baseline_dir / "run_data"
    baseline = load_json(baseline_candidate_report_path)
    baseline_map = {
        f"{row['strategy']}:{row['symbol']}:{row['timeframe']}": row
        for row in baseline.get("rows", [])
        if isinstance(row, dict)
    }
    targets = select_targets(baseline, target_route_limit, max_watchlist_targets, selection_mode)

    targets_payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "baseline_candidate_report": relative(baseline_candidate_report_path),
        "selection_mode": selection_mode,
        "target_limit": target_route_limit,
        "targets": [route.key for route in targets],
    }
    targets_json = out_dir / "auto_tune_targets.json"
    write_json(targets_json, targets_payload)

    route_summaries: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, route_parallel)) as executor:
        future_map = {}
        for route in targets:
            base_row = baseline_map.get(route.key)
            if not isinstance(base_row, dict):
                continue
            future = executor.submit(
                process_route,
                route,
                route_runs_dir,
                baseline_candidate_report_path,
                baseline_summary_path,
                baseline_result_list_path,
                baseline_data_root,
                base_row,
                provisional_core_min_trades,
                stop_on_confirmed_core,
                auto_run_regime,
                regime_block_ratio,
                selection_mode,
            )
            future_map[future] = route.key
        for future in as_completed(future_map):
            route_key = future_map[future]
            try:
                route_summaries.append(future.result())
            except subprocess.CalledProcessError as exc:
                route_summaries.append(
                    {
                        "route": route_key,
                        "baseline": route_metrics(baseline_map.get(route_key)),
                        "stages": [],
                        "selected_stage": "failed",
                        "selected": {},
                        "final_state": "route_failed",
                        "next_action": f"rerun_with_lower_parallelism: exit={exc.returncode}",
                    }
                )
            except Exception as exc:  # noqa: BLE001
                route_summaries.append(
                    {
                        "route": route_key,
                        "baseline": route_metrics(baseline_map.get(route_key)),
                        "stages": [],
                        "selected_stage": "failed",
                        "selected": {},
                        "final_state": "route_failed",
                        "next_action": f"unexpected_error: {type(exc).__name__}",
                    }
                )
    route_summaries.sort(key=lambda item: str(item.get("route", "")))

    summary_payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "out_dir": relative(out_dir),
        "baseline_candidate_report": relative(baseline_candidate_report_path),
        "targets_json": relative(targets_json),
        "selection_mode": selection_mode,
        "targets": [route.key for route in targets],
        "route_summaries": route_summaries,
        "provisional_core_min_trades": provisional_core_min_trades,
        "route_parallel": route_parallel,
        "stage_data_parallel": parallel_settings["stage_data_parallel"],
        "stage_case_parallel": parallel_settings["stage_case_parallel"],
        "hold_case_parallel": parallel_settings["hold_case_parallel"],
        "regime_case_parallel": parallel_settings["regime_case_parallel"],
    }
    summary_json = out_dir / "auto_tune_summary.json"
    write_json(summary_json, summary_payload)

    lines: list[str] = []
    lines.append("# Core Route Autotune Summary")
    lines.append("")
    lines.append(f"- generated_at: {summary_payload['generated_at']}")
    lines.append(f"- out_dir: {summary_payload['out_dir']}")
    lines.append(f"- baseline_candidate_report: {summary_payload['baseline_candidate_report']}")
    lines.append(f"- selection_mode: {selection_mode}")
    target_keys = summary_payload.get("targets", [])
    targets_text = (
        ", ".join(str(item) for item in target_keys)
        if isinstance(target_keys, list) and target_keys
        else "-"
    )
    lines.append(f"- targets: {targets_text}")
    lines.append(f"- provisional_core_min_trades: {provisional_core_min_trades}")
    lines.append(f"- route_parallel: {route_parallel}")
    lines.append(f"- stage_data_parallel: {parallel_settings['stage_data_parallel']}")
    lines.append(f"- stage_case_parallel: {parallel_settings['stage_case_parallel']}")
    lines.append(f"- hold_case_parallel: {parallel_settings['hold_case_parallel']}")
    lines.append(f"- regime_case_parallel: {parallel_settings['regime_case_parallel']}")
    lines.append("")
    lines.append(
        "| Route | Baseline | Selected Stage | Final State | Final Candidate | "
        "PF | EXPbps | PeriodPnL | DD | Trades | Next Action |"
    )
    lines.append("|---|---|---|---|---|---:|---:|---:|---:|---:|---|")
    for item in route_summaries:
        selected = item.get("selected", {})
        baseline_metrics = item.get("baseline", {})
        lines.append(
            (
                "| {route} | {baseline_status} | {stage} | {state} | {status} | "
                "{pf:.3f} | {exp:.2f} | {pnl:.3f} | {dd:.5f} | "
                "{trades:.2f} | {next_action} |"
            ).format(
                route=str(item.get("route", "")),
                baseline_status=str(baseline_metrics.get("candidate_status", "")),
                stage=str(item.get("selected_stage", "")),
                state=str(item.get("final_state", "")),
                status=str(selected.get("candidate_status", "")),
                pf=safe_float(selected.get("pf_mean", 0.0)),
                exp=safe_float(selected.get("expectancy_bps_mean", 0.0)),
                pnl=safe_float(selected.get("period_pnl_mean", 0.0)),
                dd=safe_float(selected.get("max_dd_mean", 0.0)),
                trades=safe_float(selected.get("closed_trades_mean", 0.0)),
                next_action=str(item.get("next_action", "")),
            )
        )
    lines.append("")
    for item in route_summaries:
        lines.append(f"## {item['route']}")
        lines.append("")
        baseline_metrics = item.get("baseline", {})
        lines.append(
            (
                "- baseline: status={status} pf={pf:.3f} expbps={exp:.2f} "
                "pnl={pnl:.3f} dd={dd:.5f} trades={trades:.2f}"
            ).format(
                status=str(baseline_metrics.get("candidate_status", "")),
                pf=safe_float(baseline_metrics.get("pf_mean", 0.0)),
                exp=safe_float(baseline_metrics.get("expectancy_bps_mean", 0.0)),
                pnl=safe_float(baseline_metrics.get("period_pnl_mean", 0.0)),
                dd=safe_float(baseline_metrics.get("max_dd_mean", 0.0)),
                trades=safe_float(baseline_metrics.get("closed_trades_mean", 0.0)),
            )
        )
        lines.append(
            f"- selected_stage: {item['selected_stage']} "
            f"final_state: {item['final_state']} "
            f"next_action: {item['next_action']}"
        )
        lines.append("")
        lines.append("| Stage | Candidate | PF | EXPbps | PeriodPnL | DD | Trades | Summary |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---|")
        for stage in item.get("stages", []):
            best = stage.get("best", {})
            lines.append(
                (
                    "| {stage_name} | {status} | {pf:.3f} | {exp:.2f} | "
                    "{pnl:.3f} | {dd:.5f} | {trades:.2f} | {summary_path} |"
                ).format(
                    stage_name=str(stage.get("stage", "")),
                    status=str(best.get("candidate_status", "")),
                    pf=safe_float(best.get("pf_mean", 0.0)),
                    exp=safe_float(best.get("expectancy_bps_mean", 0.0)),
                    pnl=safe_float(best.get("period_pnl_mean", 0.0)),
                    dd=safe_float(best.get("max_dd_mean", 0.0)),
                    trades=safe_float(best.get("closed_trades_mean", 0.0)),
                    summary_path=str(stage.get("summary_path", "")),
                )
            )
        lines.append("")

    summary_md = out_dir / "auto_tune_summary.md"
    summary_md.write_text("\n".join(lines), encoding="utf-8")
    print(relative(summary_json))
    print(relative(summary_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
