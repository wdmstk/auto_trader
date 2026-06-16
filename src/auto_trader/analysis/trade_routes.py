from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def build_trade_route_selection(
    report: str | Path | dict[str, Any],
    *,
    default_timeframe: str = "15m",
    seed_manifest: str | Path | dict[str, Any] | None = None,
    statistical_gate_mode: str = "hard",
) -> dict[str, Any]:
    payload = _load_obj(report)
    primary = payload.get("candidates", payload)
    probe = payload.get("range_probe_candidates", {})
    statistical = _load_obj(payload.get("statistical_qualification", {}))
    passed_route_keys = {str(value) for value in statistical.get("passed_route_keys", []) if str(value)}
    statistical_status = str(statistical.get("status", "missing"))
    dropped_routes: list[dict[str, Any]] = []

    rows = _candidate_rows(primary) + _candidate_rows(probe)
    selected: list[dict[str, Any]]
    if seed_manifest is not None:
        selected = _select_seed_routes(
            rows,
            seed_manifest=seed_manifest,
            default_timeframe=default_timeframe,
            statistical_status=statistical_status,
            passed_route_keys=passed_route_keys,
            qualification_report_path=str(statistical.get("qualification_report_path", "")),
            statistical_gate_mode=statistical_gate_mode,
            dropped_routes=dropped_routes,
        )
    else:
        core_rows = [
            row for row in rows if str(row.get("candidate_status", "")) == "core" and statistical_status == "pass" and _row_route_key(row) in passed_route_keys
        ]
        if str(statistical_gate_mode).strip().lower() == "hard":
            for row in rows:
                if str(row.get("candidate_status", "")) != "core":
                    continue
                route_key = _row_route_key(row)
                if not route_key or route_key in passed_route_keys:
                    continue
                dropped_routes.append(
                    _dropped_route_from_row(
                        row,
                        qualification_report_path=str(statistical.get("qualification_report_path", "")),
                        default_timeframe=default_timeframe,
                        reason="statistical_fail",
                    )
                )
        ordered = sorted(core_rows, key=_route_sort_key, reverse=True)
        selected_routes = [
            _selection_route_from_row(
                row,
                qualification_report_path=str(statistical.get("qualification_report_path", "")),
                default_timeframe=default_timeframe,
            )
            for row in ordered
        ]
        selected = cast(
            list[dict[str, Any]],
            [route for route in selected_routes if route is not None],
        )

    trend_symbols = [route["symbol"] for route in selected if route["strategy"] == "trend"]
    range_symbols = [route["symbol"] for route in selected if route["strategy"] == "range"]
    symbol_timeframes: dict[str, str] = {}
    for route in selected:
        symbol_timeframes.setdefault(str(route["symbol"]), str(route["timeframe"]))

    return {
        "timeframe": default_timeframe,
        "trade_routes": selected,
        "trend_enabled_symbols": _csv_symbols(trend_symbols),
        "range_enabled_symbols": _csv_symbols(range_symbols),
        "symbol_timeframes": symbol_timeframes,
        "statistical_gate_mode": statistical_gate_mode,
        "dropped_routes": dropped_routes,
    }


def _select_seed_routes(
    rows: list[dict[str, Any]],
    *,
    seed_manifest: str | Path | dict[str, Any],
    default_timeframe: str,
    statistical_status: str,
    passed_route_keys: set[str],
    qualification_report_path: str,
    statistical_gate_mode: str,
    dropped_routes: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    gate_mode = str(statistical_gate_mode).strip().lower() or "hard"
    if dropped_routes is None:
        dropped_routes = []
    if statistical_status == "missing":
        return []
    seed_payload = _load_obj(seed_manifest)
    seed_selection = seed_payload.get("selection", {}) if isinstance(seed_payload, dict) else {}
    seed_routes = seed_selection.get("trade_routes", []) if isinstance(seed_selection, dict) else []
    if not isinstance(seed_routes, list) or not seed_routes:
        seeded = resolve_live_trade_routes(seed_manifest, default_timeframe=default_timeframe)
        seed_routes = seeded.get("trade_routes", [])
    row_by_key = {_row_route_key(row): row for row in rows if isinstance(row, dict) and all(_route_fields(row))}
    selected: list[dict[str, Any]] = []
    for raw_route in seed_routes:
        if not isinstance(raw_route, dict):
            continue
        route = _route_from_row(raw_route, default_timeframe=default_timeframe)
        if route is None:
            is_fail = str(raw_route.get("statistical_status", "")).strip() != "pass"
            if gate_mode == "hard" and is_fail:
                dropped_routes.append(
                    _dropped_route_from_row(
                        raw_route,
                        qualification_report_path=qualification_report_path,
                        default_timeframe=default_timeframe,
                        reason="statistical_fail",
                    )
                )
            continue
        route_key = _row_route_key(route)
        row = row_by_key.get(route_key)
        if row is None:
            is_fail = str(raw_route.get("statistical_status", "")).strip() != "pass"
            if gate_mode == "hard" and is_fail:
                dropped_routes.append(
                    _dropped_route_from_row(
                        raw_route,
                        qualification_report_path=qualification_report_path,
                        default_timeframe=default_timeframe,
                        reason="statistical_fail",
                    )
                )
            continue
        statistical_route_status = "pass" if statistical_status == "pass" and route_key in passed_route_keys else "fail"
        candidate_status = str(row.get("candidate_status", route.get("candidate_status", "")))
        if candidate_status != "core":
            continue
        if gate_mode == "hard" and statistical_route_status != "pass":
            dropped_routes.append(
                _dropped_route_from_row(
                    row,
                    qualification_report_path=qualification_report_path,
                    default_timeframe=default_timeframe,
                    reason="statistical_fail",
                )
            )
            continue
        enriched = dict(raw_route)
        enriched.update(
            {
                "symbol": str(route["symbol"]),
                "strategy": str(route["strategy"]),
                "timeframe": str(route["timeframe"]),
                "expected_regime": str(route["expected_regime"]),
                "candidate_status": candidate_status,
                "pf_mean": _num(row.get("pf_mean", 0.0)),
                "expectancy_bps_mean": _num(row.get("expectancy_bps_mean", 0.0)),
                "period_pnl_mean": _num(row.get("period_pnl_mean", 0.0)),
                "max_dd_mean": _num(row.get("max_dd_mean", 0.0)),
                "closed_trades_mean": _num(row.get("closed_trades_mean", 0.0)),
                "candidate_score": _num(row.get("candidate_score", 0.0)),
                "statistical_status": statistical_route_status,
                "qualification_report_path": qualification_report_path,
                "route_policy": ("" if statistical_route_status == "pass" else "test-only / statistical-fail"),
            }
        )
        selected.append(enriched)
    return selected


def _dropped_route_from_row(
    row: dict[str, Any],
    *,
    qualification_report_path: str,
    default_timeframe: str,
    reason: str,
) -> dict[str, Any]:
    route = _route_from_row(row, default_timeframe=default_timeframe)
    if route is None:
        route = {
            "symbol": str(row.get("symbol", "")).strip().upper(),
            "strategy": str(row.get("strategy", "")).strip(),
            "timeframe": str(row.get("timeframe", "")).strip() or default_timeframe,
            "expected_regime": str(row.get("expected_regime", "")).strip(),
            "candidate_status": str(row.get("candidate_status", "")).strip(),
        }
    route.update(
        {
            "pf_mean": _num(row.get("pf_mean", 0.0)),
            "expectancy_bps_mean": _num(row.get("expectancy_bps_mean", 0.0)),
            "period_pnl_mean": _num(row.get("period_pnl_mean", 0.0)),
            "max_dd_mean": _num(row.get("max_dd_mean", 0.0)),
            "closed_trades_mean": _num(row.get("closed_trades_mean", 0.0)),
            "candidate_score": _num(row.get("candidate_score", 0.0)),
            "qualification_report_path": qualification_report_path,
            "route_policy": "production-drop",
            "dropped_reason": reason,
        }
    )
    return route


def _selection_route_from_row(
    row: dict[str, Any],
    *,
    qualification_report_path: str,
    default_timeframe: str,
) -> dict[str, Any] | None:
    route = _route_from_row(row, default_timeframe=default_timeframe)
    if route is None:
        return None
    route.update(
        {
            "pf_mean": _num(row.get("pf_mean", 0.0)),
            "expectancy_bps_mean": _num(row.get("expectancy_bps_mean", 0.0)),
            "period_pnl_mean": _num(row.get("period_pnl_mean", 0.0)),
            "max_dd_mean": _num(row.get("max_dd_mean", 0.0)),
            "closed_trades_mean": _num(row.get("closed_trades_mean", 0.0)),
            "candidate_score": _num(row.get("candidate_score", 0.0)),
            "statistical_status": "pass",
            "qualification_report_path": qualification_report_path,
            "route_policy": "",
        }
    )
    return route


def _route_fields(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("symbol", "")).strip().upper(),
        str(row.get("timeframe", "")).strip(),
        str(row.get("strategy", "")).strip(),
    )


def validate_trade_route_selection(selection: object) -> None:
    if not isinstance(selection, dict):
        raise ValueError("selection must be an object")
    trade_routes = selection.get("trade_routes", [])
    if not isinstance(trade_routes, list):
        raise ValueError("selection.trade_routes must be a list")
    for index, route in enumerate(trade_routes):
        if not isinstance(route, dict):
            raise ValueError(f"selection.trade_routes[{index}] must be an object")
        statistical_status = str(route.get("statistical_status", "")).strip()
        if not statistical_status:
            raise ValueError(f"selection.trade_routes[{index}].statistical_status is required")
        if statistical_status not in {"pass", "fail"}:
            raise ValueError(f"selection.trade_routes[{index}].statistical_status must be pass/fail")


def resolve_live_trade_routes(
    report: str | Path | dict[str, Any],
    *,
    default_timeframe: str = "15m",
) -> dict[str, Any]:
    payload = _load_obj(report)
    selection = payload.get("selection", {})
    if isinstance(selection, dict):
        normalized = _normalize_trade_routes(selection.get("trade_routes"), default_timeframe=default_timeframe)
        if normalized is not None:
            trade_routes = list(normalized)
            return {
                "source": "selection.trade_routes",
                "timeframe": str(selection.get("timeframe", default_timeframe)).strip() or default_timeframe,
                "trade_routes": trade_routes,
                "trend_enabled_symbols": _csv_symbols([str(route.get("symbol", "")) for route in trade_routes if str(route.get("strategy", "")) == "trend"]),
                "range_enabled_symbols": _csv_symbols([str(route.get("symbol", "")) for route in trade_routes if str(route.get("strategy", "")) == "range"]),
                "symbol_timeframes": {str(route.get("symbol", "")): str(route.get("timeframe", default_timeframe)) for route in trade_routes},
            }

        has_selection_keys = "trend_enabled_symbols" in selection or "range_enabled_symbols" in selection
        if has_selection_keys:
            timeframe = str(selection.get("timeframe", default_timeframe)).strip() or default_timeframe
            routes = _legacy_routes_from_symbols(
                trend_symbols=_csv_symbols(selection.get("trend_enabled_symbols", [])),
                range_symbols=_csv_symbols(selection.get("range_enabled_symbols", [])),
                timeframe=timeframe,
            )
            if routes is not None:
                trade_routes = list(routes)
                return {
                    "source": "selection.enabled_symbols",
                    "timeframe": timeframe,
                    "trade_routes": trade_routes,
                    "trend_enabled_symbols": _csv_symbols(
                        [str(route.get("symbol", "")) for route in trade_routes if str(route.get("strategy", "")) == "trend"]
                    ),
                    "range_enabled_symbols": _csv_symbols(
                        [str(route.get("symbol", "")) for route in trade_routes if str(route.get("strategy", "")) == "range"]
                    ),
                    "symbol_timeframes": {str(route.get("symbol", "")): str(route.get("timeframe", timeframe)) for route in trade_routes},
                }

    return {
        "source": "",
        "timeframe": default_timeframe,
        "trade_routes": [],
        "trend_enabled_symbols": [],
        "range_enabled_symbols": [],
        "symbol_timeframes": {},
    }


def _candidate_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    obj = _load_obj(payload)
    if isinstance(obj, dict):
        raw_rows = obj.get("rows", [])
        if isinstance(raw_rows, list):
            rows.extend(row for row in raw_rows if isinstance(row, dict))
        timeframe_reports = obj.get("timeframe_reports", [])
        if isinstance(timeframe_reports, list):
            for report in timeframe_reports:
                if not isinstance(report, dict):
                    continue
                nested_rows = report.get("rows", [])
                if isinstance(nested_rows, list):
                    rows.extend(row for row in nested_rows if isinstance(row, dict))
    return rows


def _normalize_trade_routes(
    value: object,
    *,
    default_timeframe: str,
) -> tuple[dict[str, Any], ...] | None:
    if not isinstance(value, list):
        return None
    routes: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        route = _route_from_row(
            item,
            default_timeframe=default_timeframe,
            preserve_metadata=True,
        )
        if route is None:
            continue
        routes.append(route)
    return tuple(routes) if routes else None


def _legacy_routes_from_symbols(
    *,
    trend_symbols: list[str] | tuple[str, ...] | None,
    range_symbols: list[str] | tuple[str, ...] | None,
    timeframe: str,
) -> tuple[dict[str, Any], ...] | None:
    routes: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    for symbol in trend_symbols or ():
        symbol = str(symbol).strip().upper()
        if not symbol or symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        routes.append(
            {
                "symbol": symbol,
                "strategy": "trend",
                "timeframe": timeframe,
                "expected_regime": "TREND",
                "candidate_status": "legacy",
            }
        )
    for symbol in range_symbols or ():
        symbol = str(symbol).strip().upper()
        if not symbol or symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        routes.append(
            {
                "symbol": symbol,
                "strategy": "range",
                "timeframe": timeframe,
                "expected_regime": "RANGE",
                "candidate_status": "legacy",
            }
        )
    return tuple(routes) if routes else None


def _route_from_row(
    row: dict[str, Any],
    *,
    default_timeframe: str,
    preserve_metadata: bool = False,
) -> dict[str, Any] | None:
    symbol = str(row.get("symbol", "")).strip().upper()
    strategy = str(row.get("strategy", "")).strip()
    if not symbol or strategy not in {"trend", "range"}:
        return None
    timeframe = str(row.get("timeframe", "")).strip() or default_timeframe
    expected_regime = str(row.get("expected_regime", "")).strip() or ("TREND" if strategy == "trend" else "RANGE")
    route: dict[str, Any] = {
        "symbol": symbol,
        "strategy": strategy,
        "timeframe": timeframe,
        "expected_regime": expected_regime,
        "candidate_status": str(row.get("candidate_status", "core")),
    }
    if preserve_metadata:
        for key in (
            "selection_source",
            "selected_stage",
            "config_label",
            "statistical_status",
            "qualification_report_path",
            "route_policy",
        ):
            if key in row:
                value = row.get(key)
                if value is not None:
                    route[key] = value
        statistical_status = str(route.get("statistical_status", "")).strip()
        if statistical_status and statistical_status != "pass" and "route_policy" not in route:
            route["route_policy"] = "test-only / statistical-fail"
        params = row.get("params")
        if isinstance(params, dict):
            route["params"] = dict(params)
    return route


def _csv_symbols(values: Any) -> list[str]:
    if isinstance(values, list):
        source = values
    elif isinstance(values, tuple):
        source = list(values)
    elif isinstance(values, str):
        source = [item.strip() for item in values.split(",") if item.strip()]
    else:
        source = []
    seen: set[str] = set()
    ordered: list[str] = []
    for value in source:
        symbol = str(value).strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)
    return ordered


def _route_sort_key(row: dict[str, Any]) -> tuple[int, float, float, float, float, str, str]:
    priority = {"core": 2, "probe": 1, "watchlist": 0}.get(str(row.get("candidate_status", "")), 0)
    return (
        priority,
        _num(row.get("candidate_score", 0.0)),
        _num(row.get("expectancy_bps_mean", 0.0)),
        _num(row.get("pf_mean", 0.0)),
        _num(row.get("period_pnl_mean", 0.0)),
        str(row.get("strategy", "")),
        str(row.get("symbol", "")),
    )


def _num(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _row_route_key(row: dict[str, Any]) -> str:
    return f"{str(row.get('strategy', '')).strip()}:" f"{str(row.get('symbol', '')).strip()}:" f"{str(row.get('timeframe', '')).strip()}"


def _load_obj(payload: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, str | Path):
        loaded = json.loads(Path(payload).read_text(encoding="utf-8"))
        return cast(dict[str, Any], loaded) if isinstance(loaded, dict) else {}
    return payload if isinstance(payload, dict) else {}
