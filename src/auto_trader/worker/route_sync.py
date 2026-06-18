from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from auto_trader.utils import parse_csv


@dataclass(frozen=True)
class TradeRouteSpec:
    symbol: str
    strategy: Literal["trend", "range"]
    timeframe: str
    expected_regime: str
    candidate_status: str = "core"
    statistical_status: str = "missing"

    def route_key(self) -> str:
        return f"{self.strategy}:{self.symbol}:{self.timeframe}"

    def to_dict(self) -> dict[str, object]:
        route_policy = ""
        if self.statistical_status != "pass":
            route_policy = "test-only / statistical-fail"
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "timeframe": self.timeframe,
            "expected_regime": self.expected_regime,
            "candidate_status": self.candidate_status,
            "statistical_status": self.statistical_status,
            "route_policy": route_policy,
            "route_key": self.route_key(),
        }


def resolve_worker_routes(
    payload: Mapping[str, object],
    *,
    execution_mode: str,
    default_timeframe: str,
) -> tuple[TradeRouteSpec, ...] | None:
    selection = payload.get("selection", {})
    if isinstance(selection, dict):
        trade_routes = _normalize_trade_routes(
            selection.get("trade_routes"),
            default_timeframe=default_timeframe,
        )
        if trade_routes is not None:
            if execution_mode != "production":
                return trade_routes
            return tuple(route for route in trade_routes if route.statistical_status == "pass")

        statistical = payload.get("statistical_qualification", {})
        if not isinstance(statistical, dict) or str(statistical.get("status", "")) != "pass":
            return ()

        has_selection_keys = "trend_enabled_symbols" in selection or "range_enabled_symbols" in selection
        if has_selection_keys:
            timeframe = str(selection.get("timeframe", default_timeframe)).strip() or default_timeframe
            trend_symbols = _normalize_symbols(selection.get("trend_enabled_symbols"))
            range_symbols = _normalize_symbols(selection.get("range_enabled_symbols"))
            routes = _legacy_routes_from_symbols(
                trend_symbols=trend_symbols,
                range_symbols=range_symbols,
                timeframe=timeframe,
            )
            if routes is not None:
                if execution_mode == "production":
                    return ()
                return routes

    candidates = payload.get("candidates", {})
    if isinstance(candidates, dict):
        routes = _routes_from_candidates(candidates, default_timeframe=default_timeframe)
        if routes is not None:
            return routes

    return None


def _routes_from_candidates(
    payload: dict[str, object],
    *,
    default_timeframe: str,
) -> tuple[TradeRouteSpec, ...] | None:
    routes: list[TradeRouteSpec] = []
    for row in _candidate_rows(payload):
        if str(row.get("candidate_status", "")) != "core":
            continue
        route = _route_from_row(row, default_timeframe=default_timeframe)
        if route is None:
            continue
        routes.append(route)
    return tuple(routes) if routes else None


def _candidate_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
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


def _normalize_trade_routes(
    value: object,
    *,
    default_timeframe: str,
) -> tuple[TradeRouteSpec, ...] | None:
    if not isinstance(value, list):
        return None
    routes: list[TradeRouteSpec] = []
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
    trend_symbols: tuple[str, ...] | None,
    range_symbols: tuple[str, ...] | None,
    timeframe: str,
) -> tuple[TradeRouteSpec, ...] | None:
    routes: list[TradeRouteSpec] = []
    for symbol in trend_symbols or ():
        routes.append(
            TradeRouteSpec(
                symbol=symbol,
                strategy="trend",
                timeframe=timeframe,
                expected_regime="TREND",
                candidate_status="legacy",
                statistical_status="missing",
            )
        )
    for symbol in range_symbols or ():
        routes.append(
            TradeRouteSpec(
                symbol=symbol,
                strategy="range",
                timeframe=timeframe,
                expected_regime="RANGE",
                candidate_status="legacy",
                statistical_status="missing",
            )
        )
    return tuple(routes) if routes else None


def _route_from_row(
    row: dict[str, object],
    *,
    default_timeframe: str,
) -> TradeRouteSpec | None:
    symbol = str(row.get("symbol", "")).strip()
    strategy = str(row.get("strategy", "")).strip()
    if not symbol or strategy not in {"trend", "range"}:
        return None
    timeframe = str(row.get("timeframe", "")).strip() or default_timeframe
    expected_regime = str(row.get("expected_regime", "")).strip()
    if not expected_regime:
        expected_regime = "TREND" if strategy == "trend" else "RANGE"
    return TradeRouteSpec(
        symbol=symbol,
        strategy=cast(Literal["trend", "range"], strategy),
        timeframe=timeframe,
        expected_regime=expected_regime,
        candidate_status=str(row.get("candidate_status", "core")),
        statistical_status=str(row.get("statistical_status", "missing")).strip() or "missing",
    )


def _normalize_symbols(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _csv_symbols(value)


def _csv_symbols(value: object) -> tuple[str, ...]:
    return parse_csv(value)
