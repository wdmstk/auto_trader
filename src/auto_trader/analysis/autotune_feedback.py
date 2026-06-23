from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from auto_trader.utils import load_json_object, safe_float, write_json_file

DEFAULT_SUMMARY_PATH = Path("data/validation/core_route_autotune/auto_tune_summary.json")
DEFAULT_OUT_DIR = Path("data/validation/core_route_autotune")
DEFAULT_OUT_JSON = DEFAULT_OUT_DIR / "autotune_core_feedback.json"
DEFAULT_OUT_ENV = DEFAULT_OUT_DIR / "autotune_core_feedback.env"
DEFAULT_OUT_MD = DEFAULT_OUT_DIR / "autotune_core_feedback.md"
DEFAULT_OUT_MANIFEST_JSON = DEFAULT_OUT_DIR / "autotune_route_manifest.json"
DEFAULT_OUT_MANIFEST_MD = DEFAULT_OUT_DIR / "autotune_route_manifest.md"
DEFAULT_OUT_FULL_MANIFEST_JSON = DEFAULT_OUT_DIR / "autotune_full_route_manifest.json"
DEFAULT_OUT_FULL_MANIFEST_MD = DEFAULT_OUT_DIR / "autotune_full_route_manifest.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build candidate runtime artifacts from core route autotune summary.")
    parser.add_argument("--summary-path", default=str(DEFAULT_SUMMARY_PATH))
    parser.add_argument("--json-path", default=str(DEFAULT_OUT_JSON))
    parser.add_argument("--env-path", default=str(DEFAULT_OUT_ENV))
    parser.add_argument("--md-path", default=str(DEFAULT_OUT_MD))
    parser.add_argument("--manifest-json-path", default=str(DEFAULT_OUT_MANIFEST_JSON))
    parser.add_argument("--manifest-md-path", default=str(DEFAULT_OUT_MANIFEST_MD))
    parser.add_argument("--full-manifest-json-path", default=str(DEFAULT_OUT_FULL_MANIFEST_JSON))
    parser.add_argument("--full-manifest-md-path", default=str(DEFAULT_OUT_FULL_MANIFEST_MD))
    parser.add_argument("--base-manifest-path", default="")
    return parser


def load_summary(path: str | Path) -> dict[str, Any]:
    return load_json_object(path)


def build_autotune_feedback(summary: str | Path | dict[str, Any]) -> dict[str, Any]:
    payload = load_summary(summary) if isinstance(summary, str | Path) else summary
    selection_mode = str(payload.get("selection_mode", "expansion")).strip() or "expansion"
    route_summaries = [row for row in payload.get("route_summaries", []) if isinstance(row, dict)]
    confirmed = [row for row in route_summaries if str(row.get("final_state", "")) in {"core_confirmed", "core_provisional"}]

    routes: list[dict[str, Any]] = []
    trend_symbols: list[str] = []
    range_symbols: list[str] = []
    all_symbols: list[str] = []

    for row in confirmed:
        route_key = str(row.get("route", ""))
        try:
            strategy, symbol, timeframe = route_key.split(":")
        except ValueError:
            continue
        symbol = symbol.strip().upper()
        selected_stage = str(row.get("selected_stage", ""))
        params = extract_effective_params(row)
        selected = row.get("selected", {}) if isinstance(row.get("selected"), dict) else {}
        route_obj = {
            "route_key": route_key,
            "strategy": strategy,
            "symbol": symbol,
            "timeframe": timeframe,
            "selected_stage": selected_stage,
            "final_state": str(row.get("final_state", "")),
            "candidate_status": str(selected.get("candidate_status", "")),
            "config_label": str(selected.get("config_label", "")),
            "pf_mean": safe_float(selected.get("pf_mean", 0.0)),
            "expectancy_bps_mean": safe_float(selected.get("expectancy_bps_mean", 0.0)),
            "period_pnl_mean": safe_float(selected.get("period_pnl_mean", 0.0)),
            "max_dd_mean": safe_float(selected.get("max_dd_mean", 0.0)),
            "closed_trades_mean": safe_float(selected.get("closed_trades_mean", 0.0)),
            "params": params,
        }
        routes.append(route_obj)
        if strategy == "trend":
            trend_symbols.append(symbol)
        elif strategy == "range":
            range_symbols.append(symbol)
        all_symbols.append(symbol)

    feedback = {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary_path": str(Path(summary)) if isinstance(summary, str | Path) else "",
        "source_out_dir": str(payload.get("out_dir", "")),
        "selection_mode": selection_mode,
        "route_count": len(routes),
        "trend_enabled_symbols": _unique(trend_symbols),
        "range_enabled_symbols": _unique(range_symbols),
        "symbols": _unique(all_symbols),
        "trade_routes": routes,
    }
    return feedback


def write_autotune_feedback(
    summary: str | Path | dict[str, Any],
    *,
    json_path: str | Path = DEFAULT_OUT_JSON,
    env_path: str | Path = DEFAULT_OUT_ENV,
    md_path: str | Path = DEFAULT_OUT_MD,
    manifest_json_path: str | Path = DEFAULT_OUT_MANIFEST_JSON,
    manifest_md_path: str | Path = DEFAULT_OUT_MANIFEST_MD,
    full_manifest_json_path: str | Path = DEFAULT_OUT_FULL_MANIFEST_JSON,
    full_manifest_md_path: str | Path = DEFAULT_OUT_FULL_MANIFEST_MD,
    base_manifest_path: str | Path = "",
) -> dict[str, Any]:
    feedback = build_autotune_feedback(summary)

    write_json_file(json_path, feedback)

    env_out = Path(env_path)
    env_out.parent.mkdir(parents=True, exist_ok=True)
    env_out.write_text(render_env(feedback), encoding="utf-8")

    md_out = Path(md_path)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(render_markdown(feedback), encoding="utf-8")

    manifest = build_route_manifest(feedback)
    write_json_file(manifest_json_path, manifest)

    manifest_md_out = Path(manifest_md_path)
    manifest_md_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_md_out.write_text(render_manifest_markdown(manifest), encoding="utf-8")

    full_manifest = build_full_route_manifest(feedback, base_manifest=base_manifest_path)
    write_json_file(full_manifest_json_path, full_manifest)

    full_manifest_md_out = Path(full_manifest_md_path)
    full_manifest_md_out.parent.mkdir(parents=True, exist_ok=True)
    full_manifest_md_out.write_text(render_manifest_markdown(full_manifest), encoding="utf-8")
    return feedback


def extract_effective_params(route_summary: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    selected_stage = str(route_summary.get("selected_stage", ""))
    stages = route_summary.get("stages", [])
    if not isinstance(stages, list):
        return params
    stage_order = [
        "hold",
        "range_matrix",
        "trend_next_step",
        "trend_entry_threshold",
        "regime_threshold",
    ]
    for stage_name in stage_order:
        for stage in stages:
            if not isinstance(stage, dict) or str(stage.get("stage", "")) != stage_name:
                continue
            best = stage.get("best", {})
            if not isinstance(best, dict):
                continue
            params.update(parse_config_label(stage_name, str(best.get("config_label", ""))))
            if stage_name == selected_stage:
                return params
    return params


def parse_config_label(stage_name: str, label: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if stage_name == "hold":
        if label.startswith("range_hold"):
            value = label.removeprefix("range_hold")
            if value.isdigit():
                params["range_max_hold_bars"] = int(value)
        elif label.startswith("trend_hold"):
            value = label.removeprefix("trend_hold")
            if value.isdigit():
                params["trend_max_hold_bars"] = int(value)
        return params

    if stage_name == "trend_next_step":
        match = re.fullmatch(r"cooldown(?P<cooldown>\d+)_exit(?P<exit>[0-9.]+)", label)
        if match:
            params["trend_reentry_cooldown_bars"] = int(match.group("cooldown"))
            params["trend_efficiency_exit_threshold"] = float(match.group("exit"))
        return params

    if stage_name == "trend_entry_threshold":
        match = re.fullmatch(
            r"cooldown(?P<cooldown>\d+)_exit(?P<exit>[0-9.]+)_breakout(?P<breakout>[0-9.]+)_momentum(?P<momentum>[0-9.]+)_pullback(?P<pullback>[0-9.]+)_higherhigh(?P<higherhigh>[0-9.]+)",
            label,
        )
        if match:
            params["trend_reentry_cooldown_bars"] = int(match.group("cooldown"))
            params["trend_efficiency_exit_threshold"] = float(match.group("exit"))
            params["trend_breakout_persistence_min"] = float(match.group("breakout"))
            params["trend_momentum_persistence_min"] = float(match.group("momentum"))
            params["trend_pullback_shallowness_min"] = float(match.group("pullback"))
            params["trend_higher_high_persistence_min"] = float(match.group("higherhigh"))
        return params

    if stage_name == "range_matrix":
        match = re.fullmatch(
            r"wick(?P<wick>[0-9.]+)_reversal(?P<reversal>true|false)_cooldown(?P<cooldown>\d+)",
            label,
        )
        if match:
            params["range_wick_ratio_min"] = float(match.group("wick"))
            params["range_require_reversal_candle"] = match.group("reversal") == "true"
            params["range_reentry_cooldown_bars"] = int(match.group("cooldown"))
        return params

    if stage_name == "regime_threshold":
        match = re.fullmatch(
            r"adx(?P<adx>[0-9.]+)_breakouthold(?P<breakouthold>\d+)_regimehold(?P<regimehold>\d+)_hvcool(?P<hvcool>\d+)",
            label,
        )
        if match:
            params["regime_trend_adx_threshold"] = float(match.group("adx"))
            params["regime_trend_breakout_persistence_min_bars"] = int(match.group("breakouthold"))
            params["min_regime_hold_bars"] = int(match.group("regimehold"))
            params["high_vol_cooldown_bars"] = int(match.group("hvcool"))
        return params

    return params


def render_env(feedback: dict[str, Any]) -> str:
    lines = [
        f"SYMBOLS={','.join(feedback['symbols'])}",
        f"TREND_ENABLED_SYMBOLS={','.join(feedback['trend_enabled_symbols'])}",
        f"RANGE_ENABLED_SYMBOLS={','.join(feedback['range_enabled_symbols'])}",
    ]
    for idx, route in enumerate(feedback.get("trade_routes", []), start=1):
        if not isinstance(route, dict):
            continue
        lines.append(f"CORE_ROUTE_{idx}_KEY={route['route_key']}")
        lines.append(f"CORE_ROUTE_{idx}_STAGE={route['selected_stage']}")
    return "\n".join(lines) + "\n"


def render_markdown(feedback: dict[str, Any]) -> str:
    lines = [
        "# Autotune Core Feedback",
        "",
        f"- generated_at: {feedback['generated_at']}",
        f"- summary_path: {feedback['summary_path']}",
        f"- source_out_dir: {feedback['source_out_dir']}",
        f"- selection_mode: {feedback.get('selection_mode', 'expansion')}",
        f"- route_count: {feedback['route_count']}",
        f"- symbols: {', '.join(feedback['symbols']) or '-'}",
        f"- trend_enabled_symbols: {', '.join(feedback['trend_enabled_symbols']) or '-'}",
        f"- range_enabled_symbols: {', '.join(feedback['range_enabled_symbols']) or '-'}",
    ]
    if str(feedback.get("selection_mode", "")) == "core_refinement":
        lines.append("- note: this feedback is a refinement delta; matching baseline core routes are replaced in the full manifest.")
    lines.extend(
        [
            "",
            "| Route | Stage | PF | EXPbps | PeriodPnL | DD | Trades | Params |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for route in feedback.get("trade_routes", []):
        if not isinstance(route, dict):
            continue
        params = route.get("params", {})
        params_text = ", ".join(f"{key}={value}" for key, value in params.items()) or "-"
        lines.append(
            ("| {route} | {stage} | {pf:.3f} | {exp:.2f} | {pnl:.3f} | {dd:.5f} | {trades:.2f} | {params} |").format(
                route=str(route.get("route_key", "")),
                stage=str(route.get("selected_stage", "")),
                pf=safe_float(route.get("pf_mean", 0.0)),
                exp=safe_float(route.get("expectancy_bps_mean", 0.0)),
                pnl=safe_float(route.get("period_pnl_mean", 0.0)),
                dd=safe_float(route.get("max_dd_mean", 0.0)),
                trades=safe_float(route.get("closed_trades_mean", 0.0)),
                params=params_text,
            )
        )
    return "\n".join(lines) + "\n"


def build_route_manifest(feedback: dict[str, Any]) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    symbol_timeframes: dict[str, str] = {}
    for route in feedback.get("trade_routes", []):
        if not isinstance(route, dict):
            continue
        symbol = str(route.get("symbol", "")).strip().upper()
        strategy = str(route.get("strategy", "")).strip()
        timeframe = str(route.get("timeframe", "")).strip()
        expected_regime = "TREND" if strategy == "trend" else "RANGE"
        symbol_timeframes.setdefault(symbol, timeframe)
        routes.append(
            {
                "symbol": symbol,
                "strategy": strategy,
                "timeframe": timeframe,
                "expected_regime": expected_regime,
                "candidate_status": str(route.get("candidate_status", "core")),
                "statistical_status": "pass",
                "selection_source": "autotune",
                "selected_stage": str(route.get("selected_stage", "")),
                "config_label": str(route.get("config_label", "")),
                "pf_mean": safe_float(route.get("pf_mean", 0.0)),
                "expectancy_bps_mean": safe_float(route.get("expectancy_bps_mean", 0.0)),
                "period_pnl_mean": safe_float(route.get("period_pnl_mean", 0.0)),
                "max_dd_mean": safe_float(route.get("max_dd_mean", 0.0)),
                "closed_trades_mean": safe_float(route.get("closed_trades_mean", 0.0)),
                "params": route.get("params", {}),
            }
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "autotune_feedback",
        "selection_mode": str(feedback.get("selection_mode", "expansion")),
        "selection": {
            "timeframe": "",
            "trade_routes": routes,
            "trend_enabled_symbols": feedback.get("trend_enabled_symbols", []),
            "range_enabled_symbols": feedback.get("range_enabled_symbols", []),
            "symbol_timeframes": symbol_timeframes,
        },
    }


def build_full_route_manifest(
    feedback: dict[str, Any],
    *,
    base_manifest: str | Path | dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary_path = Path(str(feedback.get("summary_path", "")))
    summary_payload = load_summary(summary_path) if summary_path.exists() else {}
    baseline_candidate_report = Path(str(summary_payload.get("baseline_candidate_report", "")))
    selection_mode = str(feedback.get("selection_mode", "expansion")).strip() or "expansion"

    routes_by_key: dict[str, dict[str, Any]] = {}
    base_manifest_path = Path("")
    base_manifest_payload: dict[str, Any] = {}
    if isinstance(base_manifest, dict):
        base_manifest_payload = base_manifest
    elif isinstance(base_manifest, str | Path):
        raw = str(base_manifest).strip()
        if raw:
            base_manifest_path = Path(raw)
            if base_manifest_path.exists():
                base_manifest_payload = load_summary(base_manifest_path)

    base_selection = base_manifest_payload.get("selection", {}) if isinstance(base_manifest_payload, dict) else {}
    base_routes = base_selection.get("trade_routes", []) if isinstance(base_selection, dict) else []
    if isinstance(base_routes, list) and base_routes:
        for route in base_routes:
            if not isinstance(route, dict):
                continue
            route_key = "{strategy}:{symbol}:{timeframe}".format(
                strategy=str(route.get("strategy", "")),
                symbol=str(route.get("symbol", "")),
                timeframe=str(route.get("timeframe", "")),
            )
            routes_by_key[route_key] = dict(route)
    elif baseline_candidate_report.exists():
        baseline = load_summary(baseline_candidate_report)
        for row in baseline.get("rows", []):
            if not isinstance(row, dict):
                continue
            if str(row.get("candidate_status", "")) != "core":
                continue
            symbol = str(row.get("symbol", "")).strip().upper()
            strategy = str(row.get("strategy", "")).strip()
            timeframe = str(row.get("timeframe", "")).strip()
            if not symbol or strategy not in {"trend", "range"} or not timeframe:
                continue
            route_key = f"{strategy}:{symbol}:{timeframe}"
            routes_by_key[route_key] = {
                "symbol": symbol,
                "strategy": strategy,
                "timeframe": timeframe,
                "expected_regime": "TREND" if strategy == "trend" else "RANGE",
                "candidate_status": "core",
                "statistical_status": "pass",
                "selection_source": "baseline_core",
                "selected_stage": "baseline",
                "config_label": "baseline",
                "pf_mean": safe_float(row.get("pf_mean", 0.0)),
                "expectancy_bps_mean": safe_float(row.get("expectancy_bps_mean", 0.0)),
                "period_pnl_mean": safe_float(row.get("period_pnl_mean", 0.0)),
                "max_dd_mean": safe_float(row.get("max_dd_mean", 0.0)),
                "closed_trades_mean": safe_float(row.get("closed_trades_mean", 0.0)),
                "params": {},
            }

    delta_manifest = build_route_manifest(feedback)
    selection = delta_manifest.get("selection", {})
    for route in selection.get("trade_routes", []) if isinstance(selection, dict) else []:
        if not isinstance(route, dict):
            continue
        route_key = "{strategy}:{symbol}:{timeframe}".format(
            strategy=str(route.get("strategy", "")),
            symbol=str(route.get("symbol", "")),
            timeframe=str(route.get("timeframe", "")),
        )
        routes_by_key[route_key] = dict(route)

    ordered_routes = sorted(
        routes_by_key.values(),
        key=lambda row: (
            str(row.get("strategy", "")),
            str(row.get("symbol", "")),
            str(row.get("timeframe", "")),
        ),
    )
    trend_enabled_symbols = _unique([str(row.get("symbol", "")) for row in ordered_routes if str(row.get("strategy", "")) == "trend"])
    range_enabled_symbols = _unique([str(row.get("symbol", "")) for row in ordered_routes if str(row.get("strategy", "")) == "range"])
    symbol_timeframes: dict[str, str] = {}
    for row in ordered_routes:
        symbol_timeframes.setdefault(str(row.get("symbol", "")), str(row.get("timeframe", "")))

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "autotune_feedback_full",
        "selection_mode": selection_mode,
        "base_manifest_path": str(base_manifest_path) if str(base_manifest_path) else "",
        "baseline_candidate_report": str(baseline_candidate_report),
        "selection": {
            "timeframe": "",
            "trade_routes": ordered_routes,
            "trend_enabled_symbols": trend_enabled_symbols,
            "range_enabled_symbols": range_enabled_symbols,
            "symbol_timeframes": symbol_timeframes,
        },
    }


def render_manifest_markdown(manifest: dict[str, Any]) -> str:
    selection = manifest.get("selection", {})
    routes = selection.get("trade_routes", []) if isinstance(selection, dict) else []
    trend_symbols = ", ".join(selection.get("trend_enabled_symbols", [])) if isinstance(selection, dict) else "-"
    range_symbols = ", ".join(selection.get("range_enabled_symbols", [])) if isinstance(selection, dict) else "-"
    lines = [
        "# Autotune Route Manifest",
        "",
        f"- generated_at: {manifest.get('generated_at', '')}",
        f"- source: {manifest.get('source', '')}",
        f"- selection_mode: {manifest.get('selection_mode', 'expansion')}",
        f"- trend_enabled_symbols: {trend_symbols}",
        f"- range_enabled_symbols: {range_symbols}",
    ]
    if str(manifest.get("selection_mode", "")) == "core_refinement":
        lines.append("- note: matching baseline core routes are overwritten by refinement-selected routes in this manifest.")
    lines.extend(
        [
            "",
            "| Route | Expected Regime | Statistical | Stage | Params |",
            "|---|---|---|---|---|",
        ]
    )
    for route in routes:
        if not isinstance(route, dict):
            continue
        params = route.get("params", {})
        params_text = ", ".join(f"{k}={v}" for k, v in params.items()) or "-"
        lines.append(
            "| {strategy}:{symbol}:{timeframe} | {regime} | {stat} | {stage} | {params} |".format(
                strategy=str(route.get("strategy", "")),
                symbol=str(route.get("symbol", "")),
                timeframe=str(route.get("timeframe", "")),
                regime=str(route.get("expected_regime", "")),
                stat=str(route.get("statistical_status", "")),
                stage=str(route.get("selected_stage", "")),
                params=params_text,
            )
        )
    return "\n".join(lines) + "\n"


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        v = str(value).strip().upper()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def main() -> int:
    args = build_parser().parse_args()
    feedback = write_autotune_feedback(
        args.summary_path,
        json_path=args.json_path,
        env_path=args.env_path,
        md_path=args.md_path,
        manifest_json_path=args.manifest_json_path,
        manifest_md_path=args.manifest_md_path,
        full_manifest_json_path=args.full_manifest_json_path,
        full_manifest_md_path=args.full_manifest_md_path,
        base_manifest_path=args.base_manifest_path,
    )
    print(json.dumps(feedback, ensure_ascii=True))
    print(args.json_path)
    print(args.env_path)
    print(args.md_path)
    print(args.manifest_json_path)
    print(args.manifest_md_path)
    print(args.full_manifest_json_path)
    print(args.full_manifest_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
