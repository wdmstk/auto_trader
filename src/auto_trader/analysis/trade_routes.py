from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def build_trade_route_selection(
    report: str | Path | dict[str, Any],
    *,
    default_timeframe: str = "15m",
) -> dict[str, Any]:
    payload = _load_obj(report)
    primary = payload.get("candidates", payload)
    probe = payload.get("range_probe_candidates", {})

    rows = _candidate_rows(primary) + _candidate_rows(probe)
    core_rows = [row for row in rows if str(row.get("candidate_status", "")) == "core"]
    ordered = sorted(core_rows, key=_route_sort_key, reverse=True)

    selected: list[dict[str, Any]] = []
    for row in ordered:
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            continue
        strategy = str(row.get("strategy", "")).strip()
        if strategy not in {"trend", "range"}:
            continue
        timeframe = str(row.get("timeframe", "")).strip() or default_timeframe
        selected.append(
            {
                "symbol": symbol,
                "strategy": strategy,
                "timeframe": timeframe,
                "expected_regime": "TREND" if strategy == "trend" else "RANGE",
                "candidate_status": str(row.get("candidate_status", "")),
                "pf_mean": _num(row.get("pf_mean", 0.0)),
                "expectancy_bps_mean": _num(row.get("expectancy_bps_mean", 0.0)),
                "period_pnl_mean": _num(row.get("period_pnl_mean", 0.0)),
                "max_dd_mean": _num(row.get("max_dd_mean", 0.0)),
                "closed_trades_mean": _num(row.get("closed_trades_mean", 0.0)),
                "candidate_score": _num(row.get("candidate_score", 0.0)),
            }
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
    }


def resolve_live_trade_routes(
    report: str | Path | dict[str, Any],
    *,
    default_timeframe: str = "15m",
) -> dict[str, Any]:
    payload = _load_obj(report)
    selection = payload.get("selection", {})
    if isinstance(selection, dict):
        normalized = _normalize_trade_routes(
            selection.get("trade_routes"), default_timeframe=default_timeframe
        )
        if normalized is not None:
            trade_routes = list(normalized)
            return {
                "source": "selection.trade_routes",
                "timeframe": str(selection.get("timeframe", default_timeframe)).strip()
                or default_timeframe,
                "trade_routes": trade_routes,
                "trend_enabled_symbols": _csv_symbols(
                    [
                        str(route.get("symbol", ""))
                        for route in trade_routes
                        if str(route.get("strategy", "")) == "trend"
                    ]
                ),
                "range_enabled_symbols": _csv_symbols(
                    [
                        str(route.get("symbol", ""))
                        for route in trade_routes
                        if str(route.get("strategy", "")) == "range"
                    ]
                ),
                "symbol_timeframes": {
                    str(route.get("symbol", "")): str(route.get("timeframe", default_timeframe))
                    for route in trade_routes
                },
            }

        has_selection_keys = (
            "trend_enabled_symbols" in selection or "range_enabled_symbols" in selection
        )
        if has_selection_keys:
            timeframe = (
                str(selection.get("timeframe", default_timeframe)).strip() or default_timeframe
            )
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
                        [
                            str(route.get("symbol", ""))
                            for route in trade_routes
                            if str(route.get("strategy", "")) == "trend"
                        ]
                    ),
                    "range_enabled_symbols": _csv_symbols(
                        [
                            str(route.get("symbol", ""))
                            for route in trade_routes
                            if str(route.get("strategy", "")) == "range"
                        ]
                    ),
                    "symbol_timeframes": {
                        str(route.get("symbol", "")): str(route.get("timeframe", timeframe))
                        for route in trade_routes
                    },
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
        route = _route_from_row(item, default_timeframe=default_timeframe)
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


def _route_from_row(row: dict[str, Any], *, default_timeframe: str) -> dict[str, Any] | None:
    symbol = str(row.get("symbol", "")).strip().upper()
    strategy = str(row.get("strategy", "")).strip()
    if not symbol or strategy not in {"trend", "range"}:
        return None
    timeframe = str(row.get("timeframe", "")).strip() or default_timeframe
    expected_regime = str(row.get("expected_regime", "")).strip() or (
        "TREND" if strategy == "trend" else "RANGE"
    )
    return {
        "symbol": symbol,
        "strategy": strategy,
        "timeframe": timeframe,
        "expected_regime": expected_regime,
        "candidate_status": str(row.get("candidate_status", "core")),
    }


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


def _load_obj(payload: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, str | Path):
        loaded = json.loads(Path(payload).read_text(encoding="utf-8"))
        return cast(dict[str, Any], loaded) if isinstance(loaded, dict) else {}
    return payload if isinstance(payload, dict) else {}
