from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def build_weekly_revalidation_report(
    market_summary: str | Path | dict[str, Any],
    limit_summary: str | Path | dict[str, Any],
    *,
    symbol_gating: str | Path | dict[str, Any] | None = None,
    candidate_report: str | Path | dict[str, Any] | None = None,
    drift_report: str | Path | dict[str, Any] | None = None,
    statistical_report: str | Path | dict[str, Any] | None = None,
    timeframe: str = "15m",
) -> dict[str, Any]:
    market_rows = _load_rows(market_summary)
    limit_rows = _load_rows(limit_summary)
    gating = _load_obj(symbol_gating) if symbol_gating is not None else {}
    candidate = _load_obj(candidate_report) if candidate_report is not None else {}
    drift = _load_obj(drift_report) if drift_report is not None else {}
    statistical = _load_obj(statistical_report) if statistical_report is not None else {}

    selected_symbols = {
        "trend": _csv_symbols(gating.get("trend_enabled_symbols", [])),
        "range": _csv_symbols(gating.get("range_enabled_symbols", [])),
    }
    market = _summarize(market_rows, selected_symbols=selected_symbols, timeframe=timeframe)
    limit = _summarize(limit_rows, selected_symbols=selected_symbols, timeframe=timeframe)

    drift_status = str(drift.get("status", "unknown"))
    statistical_status = str(statistical.get("status", "missing")) if statistical else "missing"
    candidate = _apply_statistical_to_candidate(candidate, statistical)
    market_status = str(market["status"])
    limit_status = str(limit["status"])
    status = (
        "pass"
        if market_status == "pass"
        and drift_status not in {"warn", "fail"}
        and statistical_status == "pass"
        else "warn"
    )
    decision = {
        "status": status,
        "market_reason": _check_reason("market", market["checks"], market_status),
        "limit_reason": _check_reason("limit", limit["checks"], limit_status),
        "drift_reason": _drift_reason(drift_status, drift),
        "candidate_reason": _candidate_reason(candidate),
        "statistical_reason": _statistical_reason(statistical_status, statistical),
    }

    return {
        "schema_version": "1.2",
        "status": status,
        "market_status": market_status,
        "limit_status": limit_status,
        "decision": decision,
        "metrics": market["metrics"],
        "limit_metrics": limit["metrics"],
        "checks": market["checks"],
        "limit_checks": limit["checks"],
        "selection": {
            "timeframe": timeframe,
            "trend_enabled_symbols": selected_symbols["trend"],
            "range_enabled_symbols": selected_symbols["range"],
            "symbol_gating": gating,
        },
        "candidates": candidate,
        "candidate_summary": _candidate_summary(candidate),
        "symbol_summary": _candidate_summary(candidate).get("symbol_counts", {}),
        "drift": {
            "status": drift_status,
            "drift_trade_block": bool(drift.get("drift_trade_block", False)),
            "fail_feature_ratio": float(drift.get("fail_feature_ratio", 0.0) or 0.0),
            "missing_feature_ratio": float(drift.get("missing_feature_ratio", 0.0) or 0.0),
            "report_path": str(drift.get("report_path", "")),
        },
        "statistical_qualification": statistical,
    }


def _summarize(
    rows: list[dict[str, Any]],
    *,
    selected_symbols: dict[str, list[str]],
    timeframe: str,
) -> dict[str, Any]:
    trend = _metrics(
        rows, strategy="trend", selected_symbols=selected_symbols["trend"], timeframe=timeframe
    )
    range_ = _metrics(
        rows, strategy="range", selected_symbols=selected_symbols["range"], timeframe=timeframe
    )

    checks = {
        "trend_pf_ge_1_2": trend["pf"] >= 1.2,
        "trend_expbps_gt_0": trend["exp_bps"] > 0.0,
        "trend_period_pnl_gt_0": trend["period_pnl"] > 0.0,
        "trend_dd_le_0_08": trend["dd"] <= 0.08,
        "range_pf_ge_1_2": range_["pf"] >= 1.2,
        "range_expbps_gt_0": range_["exp_bps"] > 0.0,
        "range_period_pnl_gt_0": range_["period_pnl"] > 0.0,
        "range_dd_le_0_08": range_["dd"] <= 0.08,
    }
    status = "pass" if all(checks.values()) else "warn"
    return {
        "status": status,
        "metrics": {
            "trend": trend,
            "range": range_,
        },
        "checks": checks,
    }


def _metrics(
    rows: list[dict[str, Any]],
    *,
    strategy: str,
    selected_symbols: list[str],
    timeframe: str,
) -> dict[str, float]:
    if not selected_symbols:
        return {"pf": 0.0, "exp_bps": 0.0, "period_pnl": 0.0, "dd": 0.0}

    filtered = [
        row
        for row in rows
        if str(row.get("strategy", "")) == strategy and str(row.get("timeframe", "")) == timeframe
    ]
    selected = set(selected_symbols)
    filtered = [row for row in filtered if str(row.get("symbol", "")) in selected]

    return {
        "pf": _mean(filtered, "pf_mean"),
        "exp_bps": _mean(filtered, "expectancy_bps_mean"),
        "period_pnl": _mean(filtered, "period_pnl_mean"),
        "dd": _mean(filtered, "max_dd_mean"),
    }


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    vals = [float(row.get(key, 0.0)) for row in rows]
    return sum(vals) / len(vals) if vals else 0.0


def _load_rows(summary: str | Path | dict[str, Any]) -> list[dict[str, Any]]:
    payload = _load_obj(summary)
    if isinstance(payload, dict):
        rows = payload.get("rows", [])
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _load_obj(payload: str | Path | dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, str | Path):
        loaded = json.loads(Path(payload).read_text(encoding="utf-8"))
        return cast(dict[str, Any], loaded) if isinstance(loaded, dict) else {}
    return payload if isinstance(payload, dict) else {}


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
        symbol = str(value).strip()
        if symbol and symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)
    return ordered


def _check_reason(label: str, checks: dict[str, bool], status: str) -> dict[str, Any]:
    if not checks:
        return {
            "status": status,
            "reason": f"{label} checks unavailable",
            "failed_checks": [],
            "passed_checks": [],
        }
    failed = [name for name, ok in checks.items() if not ok]
    passed = [name for name, ok in checks.items() if ok]
    if not failed:
        return {
            "status": status,
            "reason": f"{label} criteria satisfied",
            "failed_checks": [],
            "passed_checks": passed,
        }
    return {
        "status": status,
        "reason": f"{label} failed: {', '.join(failed)}",
        "failed_checks": failed,
        "passed_checks": passed,
    }


def _drift_reason(status: str, drift: dict[str, Any]) -> dict[str, Any]:
    if not drift:
        return {
            "status": status,
            "reason": "drift report unavailable",
        }
    if status == "pass":
        return {
            "status": status,
            "reason": "drift criteria satisfied",
        }
    if status == "fail":
        return {
            "status": status,
            "reason": "drift fail: feature distribution mismatch",
        }
    return {
        "status": status,
        "reason": "drift warn: review feature distribution shifts",
    }


def _candidate_reason(candidate: dict[str, Any]) -> dict[str, Any]:
    summary = _candidate_summary(candidate)
    return {
        "status": str(candidate.get("status", "unknown")),
        "reason": (
            f"core routes={summary['route_counts']['core']}, "
            f"probe routes={summary['route_counts']['probe']}, "
            f"watchlist routes={summary['route_counts']['watchlist']}"
        ),
        "limit_metrics": summary["limit_metrics"],
    }


def _statistical_reason(status: str, report: dict[str, Any]) -> dict[str, Any]:
    if not report:
        return {"status": "missing", "reason": "statistical qualification report unavailable"}
    failed_routes = [
        str(row.get("route_key", ""))
        for row in report.get("routes", [])
        if isinstance(row, dict) and str(row.get("status", "")) != "pass"
    ]
    return {
        "status": status,
        "reason": (
            "statistical qualification satisfied"
            if status == "pass"
            else f"statistical qualification failed: {len(failed_routes)} routes"
        ),
        "failed_routes": failed_routes,
        "report_path": str(report.get("qualification_report_path", "")),
    }


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    core = _csv_symbols(candidate.get("core_symbols", []))
    probe = _csv_symbols(candidate.get("probe_symbols", []))
    watchlist = _csv_symbols(candidate.get("watchlist_symbols", []))
    route_counts = candidate.get("route_counts", candidate.get("candidate_counts", {}))
    if not isinstance(route_counts, dict):
        route_counts = {}
    symbol_counts = candidate.get("symbol_counts", {})
    if not isinstance(symbol_counts, dict):
        symbol_counts = {}
    limit_metrics = candidate.get("limit_metrics", {})
    if not isinstance(limit_metrics, dict):
        limit_metrics = {}
    return {
        "status": str(candidate.get("status", "unknown")),
        "core_symbols": core,
        "probe_symbols": probe,
        "watchlist_symbols": watchlist,
        "route_counts": {
            "core": int(route_counts.get("core", len(core)) or len(core)),
            "probe": int(route_counts.get("probe", len(probe)) or len(probe)),
            "watchlist": int(route_counts.get("watchlist", len(watchlist)) or len(watchlist)),
        },
        "symbol_counts": {
            "core": int(symbol_counts.get("core", len(core)) or len(core)),
            "probe": int(symbol_counts.get("probe", len(probe)) or len(probe)),
            "watchlist": int(symbol_counts.get("watchlist", len(watchlist)) or len(watchlist)),
        },
        "core_count": int(route_counts.get("core", len(core)) or len(core)),
        "probe_count": int(route_counts.get("probe", len(probe)) or len(probe)),
        "watchlist_count": int(route_counts.get("watchlist", len(watchlist)) or len(watchlist)),
        "limit_metrics": limit_metrics,
    }


def _apply_statistical_to_candidate(
    candidate: dict[str, Any], statistical: dict[str, Any]
) -> dict[str, Any]:
    if not candidate:
        return candidate
    passed = {str(value) for value in statistical.get("passed_route_keys", []) if str(value)}
    statistical_status = str(statistical.get("status", "missing"))
    out = dict(candidate)
    rows = candidate.get("rows", [])
    if isinstance(rows, list):
        qualified_rows: list[dict[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            route_key = (
                f"{str(row.get('strategy', '')).strip()}:"
                f"{str(row.get('symbol', '')).strip()}:"
                f"{str(row.get('timeframe', '')).strip()}"
            )
            row["statistical_status"] = (
                "pass" if statistical_status == "pass" and route_key in passed else "fail"
            )
            if row.get("candidate_status") == "core" and row["statistical_status"] != "pass":
                row["candidate_status"] = "watchlist"
            qualified_rows.append(row)
        out["rows"] = qualified_rows
    return out
