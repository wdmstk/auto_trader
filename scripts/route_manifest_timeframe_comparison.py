#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from auto_trader.analysis.candidates import CandidateThresholds, write_candidate_report
from auto_trader.analysis.trade_routes import resolve_live_trade_routes

ROOT_DIR = Path(__file__).resolve().parent.parent

PARAM_ENV_MAP = {
    "range_wick_ratio_min": "RANGE_WICK_RATIO_MIN",
    "range_require_reversal_candle": "RANGE_REQUIRE_REVERSAL_CANDLE",
    "range_reentry_cooldown_bars": "RANGE_REENTRY_COOLDOWN_BARS",
    "range_max_hold_bars": "RANGE_MAX_HOLD_BARS",
    "trend_reentry_cooldown_bars": "TREND_REENTRY_COOLDOWN_BARS",
    "trend_efficiency_exit_threshold": "TREND_EFFICIENCY_EXIT_THRESHOLD",
    "trend_breakout_persistence_min": "TREND_BREAKOUT_PERSISTENCE_MIN",
    "trend_momentum_persistence_min": "TREND_MOMENTUM_PERSISTENCE_MIN",
    "trend_pullback_shallowness_min": "TREND_PULLBACK_SHALLOWNESS_MIN",
    "trend_higher_high_persistence_min": "TREND_HIGHER_HIGH_PERSISTENCE_MIN",
    "trend_max_hold_bars": "TREND_MAX_HOLD_BARS",
    "regime_trend_adx_threshold": "REGIME_TREND_ADX_THRESHOLD",
    "regime_trend_breakout_persistence_min_bars": "REGIME_TREND_BREAKOUT_PERSISTENCE_MIN_BARS",
    "min_regime_hold_bars": "MIN_REGIME_HOLD_BARS",
    "high_vol_cooldown_bars": "HIGH_VOL_COOLDOWN_BARS",
}


def _num_env(name: str, default: str) -> str:
    return str(os.environ.get(name, default)).strip() or default


def _safe_key(route: dict[str, Any]) -> str:
    return "{strategy}_{symbol}_{timeframe}".format(
        strategy=str(route.get("strategy", "")),
        symbol=str(route.get("symbol", "")),
        timeframe=str(route.get("timeframe", "")),
    )


def _copy_analysis_artifacts(
    route_dir: Path, aggregate_analysis_dir: Path, route: dict[str, Any]
) -> None:
    stamp = "{symbol}_{timeframe}_{strategy}".format(
        symbol=str(route.get("symbol", "")).strip().upper(),
        timeframe=str(route.get("timeframe", "")).strip(),
        strategy=str(route.get("strategy", "")).strip(),
    )
    source_dir = route_dir / "run_data" / "analysis"
    if not source_dir.exists():
        return
    aggregate_analysis_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("summary", "closed_trades", "portfolio"):
        src = source_dir / f"walkforward_{stamp}_{suffix}.parquet"
        if src.exists():
            shutil.copy2(src, aggregate_analysis_dir / src.name)


def _thresholds_from_env() -> CandidateThresholds:
    return CandidateThresholds(
        core_min_pf=float(_num_env("CORE_MIN_PF", "1.2")),
        core_min_expectancy_bps=float(_num_env("CORE_MIN_EXPECTANCY_BPS", "0.0")),
        core_min_period_pnl=float(_num_env("CORE_MIN_PERIOD_PNL", "0.0")),
        core_max_drawdown=float(_num_env("CORE_MAX_DRAWDOWN", "0.08")),
        probe_min_pf=float(_num_env("PROBE_MIN_PF", "0.8")),
        probe_min_expectancy_bps=float(_num_env("PROBE_MIN_EXPECTANCY_BPS", "0.0")),
        probe_min_period_pnl=float(_num_env("PROBE_MIN_PERIOD_PNL", "0.0")),
        probe_max_drawdown=float(_num_env("PROBE_MAX_DRAWDOWN", "0.15")),
        min_closed_trades=float(_num_env("MIN_CLOSED_TRADES", "1.0")),
    )


def _process_route(
    route: dict[str, Any],
    *,
    out_dir: Path,
    base_data_root: Path,
    route_data_parallel: str,
) -> tuple[dict[str, Any] | None, Path, dict[str, Any]]:
    route_dir = out_dir / "manifest_route_runs" / _safe_key(route)
    route_data_root = route_dir / "run_data"
    route_summary_path = route_dir / "timeframe_comparison_summary.json"
    route_candidate_path = route_dir / "candidate_report.json"
    route_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "BASE_DATA_ROOT": str(base_data_root),
            "DATA_ROOT": str(route_data_root),
            "OUTPUT_DIR": str(route_dir),
            "SUMMARY_PATH": str(route_summary_path),
            "CANDIDATE_REPORT_PATH": str(route_candidate_path),
            "SYMBOLS": str(route.get("symbol", "")),
            "TIMEFRAMES": str(route.get("timeframe", "")),
            "STRATEGIES": str(route.get("strategy", "")),
            "PARALLEL": route_data_parallel,
            "RANGE_ENABLED_SYMBOLS": str(route.get("symbol", ""))
            if str(route.get("strategy", "")) == "range"
            else "",
            "TREND_ENABLED_SYMBOLS": str(route.get("symbol", ""))
            if str(route.get("strategy", "")) == "trend"
            else "",
        }
    )
    for key, value in (
        route.get("params", {}).items() if isinstance(route.get("params", {}), dict) else []
    ):
        env_name = PARAM_ENV_MAP.get(str(key))
        if env_name:
            env[env_name] = str(value).lower() if isinstance(value, bool) else str(value)
    print(
        "[weekly-manifest] start {strategy}:{symbol}:{timeframe}".format(
            strategy=str(route.get("strategy", "")),
            symbol=str(route.get("symbol", "")),
            timeframe=str(route.get("timeframe", "")),
        ),
        flush=True,
    )
    subprocess.run(
        ["./scripts/timeframe_comparison.sh"],
        cwd=ROOT_DIR,
        env=env,
        check=True,
    )
    summary_payload = json.loads(route_summary_path.read_text(encoding="utf-8"))
    route_rows = summary_payload.get("rows", [])
    if not isinstance(route_rows, list) or not route_rows:
        return None, route_dir, route
    row = dict(route_rows[0])
    row["selection_source"] = str(route.get("selection_source", "autotune"))
    row["selected_stage"] = str(route.get("selected_stage", ""))
    row["config_label"] = str(route.get("config_label", ""))
    row["params"] = route.get("params", {})
    row["expected_regime"] = str(
        route.get(
            "expected_regime",
            "TREND" if str(route.get("strategy", "")) == "trend" else "RANGE",
        )
    )
    print(
        "[weekly-manifest] done {strategy}:{symbol}:{timeframe}".format(
            strategy=str(route.get("strategy", "")),
            symbol=str(route.get("symbol", "")),
            timeframe=str(route.get("timeframe", "")),
        ),
        flush=True,
    )
    return row, route_dir, route


def main() -> int:
    manifest_path = Path(_num_env("ROUTE_SELECTION_PATH", ""))
    if not manifest_path.exists():
        raise SystemExit(f"missing route selection manifest: {manifest_path}")

    out_dir = Path(_num_env("OUT_DIR", "data/validation/weekly_revalidation"))
    summary_path = Path(
        _num_env("MANIFEST_SUMMARY_PATH", str(out_dir / "manifest_route_summary.json"))
    )
    candidate_path = Path(
        _num_env("MANIFEST_CANDIDATE_REPORT_PATH", str(out_dir / "manifest_candidate_report.json"))
    )
    aggregate_data_root = Path(
        _num_env("MANIFEST_DATA_ROOT", str(out_dir / "manifest_route_run_data"))
    )
    base_data_root = Path(_num_env("BASE_DATA_ROOT", "data"))
    route_parallel = int(_num_env("WEEKLY_ROUTE_PARALLEL", "4"))
    route_data_parallel = _num_env("WEEKLY_ROUTE_DATA_PARALLEL", "1")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    resolved = resolve_live_trade_routes(payload, default_timeframe=_num_env("TIMEFRAMES", "15m"))
    routes = resolved.get("trade_routes", [])
    if not isinstance(routes, list) or not routes:
        raise SystemExit("no trade routes found in route selection manifest")

    route_payloads: list[dict[str, Any]] = []
    for raw_route in routes:
        if not isinstance(raw_route, dict):
            continue
        route_payloads.append(dict(raw_route))

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, route_parallel)) as executor:
        future_map = {
            executor.submit(
                _process_route,
                route,
                out_dir=out_dir,
                base_data_root=base_data_root,
                route_data_parallel=route_data_parallel,
            ): route
            for route in route_payloads
        }
        for future in as_completed(future_map):
            row, route_dir, route = future.result()
            if row is not None:
                rows.append(row)
            _copy_analysis_artifacts(route_dir, aggregate_data_root / "analysis", route)

    if not rows:
        raise SystemExit("no manifest route summaries were produced")

    rows.sort(
        key=lambda row: (
            str(row.get("strategy", "")),
            str(row.get("symbol", "")),
            str(row.get("timeframe", "")),
        )
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_payload = {
        "rows": rows,
        "source_manifest_path": str(manifest_path),
        "config": {
            "order_mode": _num_env("ORDER_MODE", "market"),
            "weekly_route_parallel": route_parallel,
            "weekly_route_data_parallel": int(route_data_parallel),
        },
    }
    summary_path.write_text(
        json.dumps(summary_payload, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    write_candidate_report(
        summary_payload, json_path=candidate_path, thresholds=_thresholds_from_env()
    )
    print(summary_path)
    print(candidate_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
