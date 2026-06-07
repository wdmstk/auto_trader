from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

DEFAULT_WEEKLY_SCRIPT_PATH = Path("scripts/weekly_strategy_revalidation.sh")
DEFAULT_REPORT_PATH = Path(
    "data/validation/symbol_candidate_exploration/timeframe_scan/candidate_report.json"
)
DEFAULT_OUT_DIR = Path("data/validation/symbol_candidate_exploration")
DEFAULT_OUT_JSON = DEFAULT_OUT_DIR / "weekly_core_feedback.json"
DEFAULT_OUT_ENV = DEFAULT_OUT_DIR / "weekly_core_feedback.env"
DEFAULT_OUT_MD = DEFAULT_OUT_DIR / "weekly_core_feedback.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an explicit weekly override from candidate core routes."
    )
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--weekly-script-path", default=str(DEFAULT_WEEKLY_SCRIPT_PATH))
    parser.add_argument("--json-path", default=str(DEFAULT_OUT_JSON))
    parser.add_argument("--env-path", default=str(DEFAULT_OUT_ENV))
    parser.add_argument("--md-path", default=str(DEFAULT_OUT_MD))
    return parser


def build_weekly_core_feedback(
    report: str | Path | dict[str, Any],
    *,
    weekly_script_path: str | Path = DEFAULT_WEEKLY_SCRIPT_PATH,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    payload = _load_obj(report)
    baseline = _parse_weekly_defaults(weekly_script_path)
    rows = _candidate_rows(payload)
    core_routes = _normalized_routes(rows, candidate_status="core")
    shadow_routes = _normalized_routes(rows, exclude_status="core")

    primary_routes = _primary_routes_by_symbol(core_routes)
    updated_trend_symbols = _merge_unique(
        baseline["trend_enabled_symbols"],
        [route["symbol"] for route in core_routes if route["strategy"] == "trend"],
    )
    updated_range_symbols = _merge_unique(
        baseline["range_enabled_symbols"],
        [route["symbol"] for route in core_routes if route["strategy"] == "range"],
    )
    updated_symbols = _merge_unique(
        baseline["symbols"],
        [route["symbol"] for route in core_routes],
    )

    route_summary = {
        "core": len(core_routes),
        "shadow": len(shadow_routes),
        "trend_core": len([route for route in core_routes if route["strategy"] == "trend"]),
        "range_core": len([route for route in core_routes if route["strategy"] == "range"]),
    }
    symbol_summary = {
        "core": len({route["symbol"] for route in core_routes}),
        "shadow": len({route["symbol"] for route in shadow_routes}),
        "trend_enabled_symbols": len(updated_trend_symbols),
        "range_enabled_symbols": len(updated_range_symbols),
    }

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "report_path": str(
            Path(report_path)
            if report_path is not None
            else Path(report)
            if isinstance(report, str | Path)
            else Path("")
        ),
        "weekly_script_path": str(Path(weekly_script_path)),
        "baseline": baseline,
        "core": {
            "trade_routes": core_routes,
            "primary_routes_by_symbol": primary_routes,
            "trend_routes": [route for route in core_routes if route["strategy"] == "trend"],
            "range_routes": [route for route in core_routes if route["strategy"] == "range"],
        },
        "shadow_routes": shadow_routes,
        "route_summary": route_summary,
        "symbol_summary": symbol_summary,
        "updated": {
            "symbols": updated_symbols,
            "trend_enabled_symbols": updated_trend_symbols,
            "range_enabled_symbols": updated_range_symbols,
            "trade_routes": core_routes,
        },
    }


def write_weekly_core_feedback(
    report: str | Path | dict[str, Any],
    *,
    weekly_script_path: str | Path = DEFAULT_WEEKLY_SCRIPT_PATH,
    report_path: str | Path | None = None,
    json_path: str | Path = DEFAULT_OUT_JSON,
    env_path: str | Path = DEFAULT_OUT_ENV,
    md_path: str | Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    feedback = build_weekly_core_feedback(
        report,
        weekly_script_path=weekly_script_path,
        report_path=report_path,
    )

    json_out = Path(json_path)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(feedback, ensure_ascii=True, indent=2), encoding="utf-8")

    env_out = Path(env_path)
    env_out.parent.mkdir(parents=True, exist_ok=True)
    env_out.write_text(_render_env(feedback), encoding="utf-8")

    md_out = Path(md_path)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(_render_markdown(feedback), encoding="utf-8")

    return feedback


def main() -> int:
    args = build_parser().parse_args()
    feedback = write_weekly_core_feedback(
        args.report_path,
        weekly_script_path=args.weekly_script_path,
        json_path=args.json_path,
        env_path=args.env_path,
        md_path=args.md_path,
    )
    print(json.dumps(feedback, ensure_ascii=True))
    print(args.json_path)
    print(args.env_path)
    print(args.md_path)
    return 0


def _parse_weekly_defaults(script_path: str | Path) -> dict[str, list[str]]:
    text = Path(script_path).read_text(encoding="utf-8")
    return {
        "symbols": _extract_csv_default(text, "SYMBOLS"),
        "trend_enabled_symbols": _extract_csv_default(text, "TREND_ENABLED_SYMBOLS"),
        "range_enabled_symbols": _extract_csv_default(text, "RANGE_ENABLED_SYMBOLS"),
    }


def _extract_csv_default(text: str, name: str) -> list[str]:
    pattern = rf'export {name}="\$\{{{name}:-([^"]*)\}}"'
    match = re.search(pattern, text)
    if not match:
        return []
    return _ordered_unique(match.group(1).split(","))


def _candidate_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw_rows = payload.get("rows", [])
    if isinstance(raw_rows, list):
        rows.extend(row for row in raw_rows if isinstance(row, dict))
    timeframe_reports = payload.get("timeframe_reports", [])
    if isinstance(timeframe_reports, list):
        for report in timeframe_reports:
            if not isinstance(report, dict):
                continue
            nested_rows = report.get("rows", [])
            if isinstance(nested_rows, list):
                rows.extend(row for row in nested_rows if isinstance(row, dict))
    return rows


def _primary_routes_by_symbol(routes: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    grouped: dict[str, dict[str, str]] = {}
    for route in routes:
        symbol = route["symbol"]
        if symbol not in grouped:
            grouped[symbol] = route
    return grouped


def _normalize_route(row: dict[str, Any]) -> dict[str, str] | None:
    symbol = str(row.get("symbol", "")).strip().upper()
    strategy = str(row.get("strategy", "")).strip()
    timeframe = str(row.get("timeframe", "")).strip()
    if not symbol or strategy not in {"trend", "range"} or not timeframe:
        return None
    expected_regime = str(row.get("expected_regime", "")).strip() or (
        "TREND" if strategy == "trend" else "RANGE"
    )
    return {
        "symbol": symbol,
        "strategy": strategy,
        "timeframe": timeframe,
        "expected_regime": expected_regime,
        "candidate_status": str(row.get("candidate_status", "")),
        "route_key": f"{strategy}:{symbol}:{timeframe}",
    }


def _normalized_routes(
    rows: list[dict[str, Any]],
    *,
    candidate_status: str | None = None,
    exclude_status: str | None = None,
) -> list[dict[str, str]]:
    routes: list[dict[str, str]] = []
    for row in rows:
        status = str(row.get("candidate_status", ""))
        if candidate_status is not None and status != candidate_status:
            continue
        if exclude_status is not None and status == exclude_status:
            continue
        route = _normalize_route(row)
        if route is not None:
            routes.append(route)
    return routes


def _merge_unique(values: Iterable[str], extra: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in list(values) + list(extra):
        symbol = str(value).strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def _ordered_unique(values: Iterable[str]) -> list[str]:
    return _merge_unique([], values)


def _load_obj(payload: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, str | Path):
        loaded = json.loads(Path(payload).read_text(encoding="utf-8"))
        return cast(dict[str, Any], loaded) if isinstance(loaded, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _render_env(feedback: dict[str, Any]) -> str:
    updated = feedback["updated"]
    return (
        "\n".join(
            [
                f"SYMBOLS={','.join(updated['symbols'])}",
                f"TREND_ENABLED_SYMBOLS={','.join(updated['trend_enabled_symbols'])}",
                f"RANGE_ENABLED_SYMBOLS={','.join(updated['range_enabled_symbols'])}",
            ]
        )
        + "\n"
    )


def _render_markdown(feedback: dict[str, Any]) -> str:
    baseline = feedback["baseline"]
    core = feedback["core"]
    updated = feedback["updated"]
    lines = [
        "# Weekly Core Feedback",
        "",
        f"- generated_at: {feedback['generated_at']}",
        f"- report_path: {feedback['report_path']}",
        f"- weekly_script_path: {feedback['weekly_script_path']}",
        f"- route_summary: {feedback['route_summary']}",
        f"- symbol_summary: {feedback['symbol_summary']}",
        "",
        "## Baseline",
        f"- SYMBOLS: {', '.join(baseline['symbols']) or '-'}",
        f"- TREND_ENABLED_SYMBOLS: {', '.join(baseline['trend_enabled_symbols']) or '-'}",
        f"- RANGE_ENABLED_SYMBOLS: {', '.join(baseline['range_enabled_symbols']) or '-'}",
        "",
        "## Core Routes",
    ]
    for route in core["trade_routes"]:
        lines.append(
            f"- {route['route_key']} ({route['candidate_status']}, {route['expected_regime']})"
        )
    lines.extend(
        [
            "",
            "## Shadow Routes",
        ]
    )
    shadow_routes = feedback["shadow_routes"]
    if shadow_routes:
        for route in shadow_routes:
            lines.append(
                f"- {route['route_key']} ({route['candidate_status']}, {route['expected_regime']})"
            )
    else:
        lines.append("- -")
    lines.extend(
        [
            "",
            "## Updated",
            f"- SYMBOLS: {', '.join(updated['symbols']) or '-'}",
            f"- TREND_ENABLED_SYMBOLS: {', '.join(updated['trend_enabled_symbols']) or '-'}",
            f"- RANGE_ENABLED_SYMBOLS: {', '.join(updated['range_enabled_symbols']) or '-'}",
            "",
            "## Apply",
            "```bash",
            "./scripts/weekly_strategy_revalidation_with_core.sh",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
