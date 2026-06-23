from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pandas as pd

from auto_trader.analysis.trade_routes import resolve_live_trade_routes
from auto_trader.utils import load_json_object, load_json_rows, parse_csv


def build_weekly_revalidation_report(
    market_summary: str | Path | dict[str, Any],
    limit_summary: str | Path | dict[str, Any],
    *,
    symbol_gating: str | Path | dict[str, Any] | None = None,
    candidate_report: str | Path | dict[str, Any] | None = None,
    drift_report: str | Path | dict[str, Any] | None = None,
    statistical_report: str | Path | dict[str, Any] | None = None,
    route_selection: str | Path | dict[str, Any] | None = None,
    manifest_vs_weekly_diff: str | Path | dict[str, Any] | None = None,
    portfolio_risk_eval: str | Path | dict[str, Any] | None = None,
    timeframe: str = "15m",
    statistical_gate_mode: str = "hard",
    run_id: str = "",
    generated_at: str = "",
) -> dict[str, Any]:
    market_rows = _load_rows(market_summary)
    limit_rows = _load_rows(limit_summary)
    gating = _load_obj(symbol_gating) if symbol_gating is not None else {}
    candidate = _load_obj(candidate_report) if candidate_report is not None else {}
    drift = _load_obj(drift_report) if drift_report is not None else {}
    statistical = _load_obj(statistical_report) if statistical_report is not None else {}
    holdout_diff = _load_obj(manifest_vs_weekly_diff) if manifest_vs_weekly_diff is not None else {}
    risk_eval = _load_risk_eval(portfolio_risk_eval)

    selected_symbols = {
        "trend": _csv_symbols(gating.get("trend_enabled_symbols", [])),
        "range": _csv_symbols(gating.get("range_enabled_symbols", [])),
    }
    selected_routes = resolve_live_trade_routes(route_selection, default_timeframe=timeframe).get("trade_routes", []) if route_selection is not None else []
    market = _summarize(
        market_rows,
        selected_symbols=selected_symbols,
        timeframe=timeframe,
        selected_routes=selected_routes if isinstance(selected_routes, list) else [],
    )
    limit = _summarize(
        limit_rows,
        selected_symbols=selected_symbols,
        timeframe=timeframe,
        selected_routes=selected_routes if isinstance(selected_routes, list) else [],
    )

    drift_status = str(drift.get("status", "unknown"))
    statistical_status = str(statistical.get("status", "missing")) if statistical else "missing"
    candidate = _apply_statistical_to_candidate(candidate, statistical)
    portfolio = _portfolio_qualification(selected_routes if isinstance(selected_routes, list) else [], statistical)
    portfolio_risk = _portfolio_risk_audit(risk_eval)
    selection_bias = _selection_bias_audit(
        selected_routes if isinstance(selected_routes, list) else [],
        statistical,
        holdout_diff if manifest_vs_weekly_diff is not None else None,
    )
    route_quality = _route_quality_audit(statistical)
    route_quality_summary = _route_quality_summary(route_quality)
    strategy_quality_summary = _strategy_quality_summary(route_quality)
    route_priority_summary = _route_priority_summary(route_quality)
    portfolio_strategy_actions = _portfolio_strategy_actions(portfolio)
    portfolio_strategy_priority_summary = _portfolio_strategy_priority_summary(portfolio)
    portfolio_next_action_summary = _portfolio_next_action_summary(portfolio, route_quality, portfolio_strategy_actions)
    portfolio_next_action_route_keys = _portfolio_next_action_route_keys(portfolio_next_action_summary)
    portfolio_qualification_gap_summary = _portfolio_qualification_gap_summary(portfolio, portfolio_next_action_route_keys)
    market_status = str(market["status"])
    limit_status = str(limit["status"])
    status = "pass" if market_status == "pass" and drift_status not in {"warn", "fail"} and statistical_status == "pass" else "warn"
    decision = {
        "status": status,
        "market_reason": _check_reason("market", market["checks"], market_status),
        "limit_reason": _check_reason("limit", limit["checks"], limit_status),
        "drift_reason": _drift_reason(drift_status, drift),
        "candidate_reason": _candidate_reason(candidate),
        "statistical_reason": _statistical_reason(statistical_status, statistical),
    }
    candidate_summary = _candidate_summary(candidate)
    drift_summary = {
        "status": drift_status,
        "drift_trade_block": bool(drift.get("drift_trade_block", False)),
        "fail_feature_ratio": float(drift.get("fail_feature_ratio", 0.0) or 0.0),
        "missing_feature_ratio": float(drift.get("missing_feature_ratio", 0.0) or 0.0),
        "report_path": str(drift.get("report_path", "")),
    }
    overview = {
        "trend_performance": market["metrics"].get("trend", {}),
        "range_performance": market["metrics"].get("range", {}),
        "candidate_summary": candidate_summary,
        "decision_status": status,
        "statistical_gate_mode": statistical_gate_mode,
        "portfolio_status": portfolio["status"],
        "portfolio_qualification_summary": {
            "status": portfolio["status"],
            "selected_route_count": portfolio["selected_route_count"],
            "qualified_route_count": portfolio["qualified_route_count"],
            "required_route_count": portfolio_qualification_gap_summary["required_route_count"],
            "missing_route_count": portfolio["missing_route_count"],
            "selected_strategy_count": portfolio["selected_strategy_count"],
            "qualified_strategy_count": portfolio["qualified_strategy_count"],
            "required_strategy_count": portfolio_qualification_gap_summary["required_strategy_count"],
            "missing_strategy_count": portfolio["missing_strategy_count"],
            "reasons": portfolio["reasons"],
            "selected_route_keys": portfolio["selected_route_keys"],
            "qualified_route_keys": portfolio["qualified_route_keys"],
            "selected_strategy_keys": portfolio["selected_strategy_keys"],
            "qualified_strategy_keys": portfolio["qualified_strategy_keys"],
        },
        "portfolio_qualification_gap_summary": portfolio_qualification_gap_summary,
        "portfolio_strategy_actions": portfolio_strategy_actions,
        "portfolio_strategy_priority_summary": portfolio_strategy_priority_summary,
        "portfolio_next_action_summary": portfolio_next_action_summary,
        "portfolio_next_action_route_keys": portfolio_next_action_route_keys,
        "portfolio_risk_status": portfolio_risk["status"],
        "selection_bias_status": selection_bias["status"],
        "selection_bias_final_holdout_summary": selection_bias["final_holdout_summary"],
        "selection_bias_final_holdout_strategy_summary": selection_bias["final_holdout_summary"].get("strategy_summary", {}),
        "route_quality_status": route_quality["status"],
        "route_quality_summary": route_quality_summary,
        "route_priority_summary": route_priority_summary,
        "strategy_quality_summary": strategy_quality_summary,
    }

    return {
        "schema_version": "1.2",
        "run_id": run_id,
        "generated_at": generated_at,
        "status": status,
        "market_status": market_status,
        "limit_status": limit_status,
        "decision": decision,
        "metrics": market["metrics"],
        "limit_metrics": limit["metrics"],
        "checks": market["checks"],
        "limit_checks": limit["checks"],
        "overview": overview,
        "selection": {
            "timeframe": timeframe,
            "trend_enabled_symbols": selected_symbols["trend"],
            "range_enabled_symbols": selected_symbols["range"],
            "symbol_gating": gating,
            "route_selection_path": (str(route_selection) if isinstance(route_selection, str | Path) else ""),
            "route_selection_source": "manifest" if selected_routes else "symbol_gating",
            "statistical_gate_mode": statistical_gate_mode,
        },
        "candidates": candidate,
        "candidate_summary": candidate_summary,
        "symbol_summary": candidate_summary.get("symbol_counts", {}),
        "drift": drift_summary,
        "feature_drift": drift_summary,
        "portfolio_qualification": portfolio,
        "portfolio_qualification_gap_summary": portfolio_qualification_gap_summary,
        "portfolio_risk_audit": portfolio_risk,
        "portfolio_strategy_actions": portfolio_strategy_actions,
        "portfolio_strategy_priority_summary": portfolio_strategy_priority_summary,
        "portfolio_next_action_summary": portfolio_next_action_summary,
        "portfolio_next_action_route_keys": portfolio_next_action_route_keys,
        "selection_bias_audit": selection_bias,
        "final_holdout_audit": selection_bias.get("final_holdout_audit", {}),
        "route_quality_audit": route_quality,
        "route_quality_summary": route_quality_summary,
        "route_priority_summary": route_priority_summary,
        "strategy_quality_summary": strategy_quality_summary,
        "statistical_qualification": statistical,
    }


def apply_manifest_vs_weekly_diff_to_report(
    report: dict[str, Any],
    manifest_vs_weekly_diff: str | Path | dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(report, dict) or manifest_vs_weekly_diff is None:
        return report
    diff = _load_obj(manifest_vs_weekly_diff)
    if not diff:
        return report
    selected_routes = report.get("selection", {}).get("trade_routes", [])
    if not isinstance(selected_routes, list):
        selected_routes = []
    statistical = report.get("statistical_qualification", {})
    if not isinstance(statistical, dict):
        statistical = {}
    audit = _selection_bias_audit(selected_routes, statistical, diff)
    report["selection_bias_audit"] = audit
    report["final_holdout_audit"] = audit.get("final_holdout_audit", {})
    overview = report.get("overview", {})
    if not isinstance(overview, dict):
        overview = {}
    overview["selection_bias_status"] = audit.get("status", "warn")
    overview["selection_bias_final_holdout_summary"] = audit.get("final_holdout_summary", {})
    overview["selection_bias_final_holdout_strategy_summary"] = audit.get("final_holdout_summary", {}).get("strategy_summary", {})
    report["overview"] = overview
    return report


def _summarize(
    rows: list[dict[str, Any]],
    *,
    selected_symbols: dict[str, list[str]],
    timeframe: str,
    selected_routes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if selected_routes:
        trend = _route_metrics(rows, strategy="trend", selected_routes=selected_routes)
        range_ = _route_metrics(rows, strategy="range", selected_routes=selected_routes)
    else:
        trend = _metrics(rows, strategy="trend", selected_symbols=selected_symbols["trend"], timeframe=timeframe)
        range_ = _metrics(rows, strategy="range", selected_symbols=selected_symbols["range"], timeframe=timeframe)

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

    filtered = [row for row in rows if str(row.get("strategy", "")) == strategy and str(row.get("timeframe", "")) == timeframe]
    selected = set(selected_symbols)
    filtered = [row for row in filtered if str(row.get("symbol", "")) in selected]

    return {
        "pf": _mean(filtered, "pf_mean"),
        "exp_bps": _mean(filtered, "expectancy_bps_mean"),
        "period_pnl": _mean(filtered, "period_pnl_mean"),
        "dd": _mean(filtered, "max_dd_mean"),
    }


def _route_metrics(
    rows: list[dict[str, Any]],
    *,
    strategy: str,
    selected_routes: list[dict[str, Any]],
) -> dict[str, float]:
    route_keys = {
        (
            str(route.get("symbol", "")).strip().upper(),
            str(route.get("timeframe", "")).strip(),
            str(route.get("strategy", "")).strip(),
        )
        for route in selected_routes
        if isinstance(route, dict) and str(route.get("strategy", "")).strip() == strategy
    }
    if not route_keys:
        return {"pf": 0.0, "exp_bps": 0.0, "period_pnl": 0.0, "dd": 0.0}
    filtered = [
        row
        for row in rows
        if (
            str(row.get("symbol", "")).strip().upper(),
            str(row.get("timeframe", "")).strip(),
            str(row.get("strategy", "")).strip(),
        )
        in route_keys
    ]
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
    return load_json_rows(summary)


def _load_risk_eval(
    payload: str | Path | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, dict):
        rows = payload.get("rows", [])
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    path = Path(payload)
    if path.suffix.lower() == ".parquet" and path.exists():
        try:
            frame = pd.read_parquet(path)
        except Exception:
            return []
        return [cast(dict[str, Any], row) for row in frame.to_dict(orient="records")]
    obj = _load_obj(path)
    rows = obj.get("rows", [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _load_obj(payload: str | Path | dict[str, Any] | None) -> dict[str, Any]:
    return load_json_object(payload)


def _csv_symbols(values: Any) -> list[str]:
    return list(parse_csv(values))


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
    failed_routes = [str(row.get("route_key", "")) for row in report.get("routes", []) if isinstance(row, dict) and str(row.get("status", "")) != "pass"]
    return {
        "status": status,
        "reason": ("statistical qualification satisfied" if status == "pass" else f"statistical qualification failed: {len(failed_routes)} routes"),
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


def _portfolio_qualification(
    selected_routes: list[dict[str, Any]],
    statistical: dict[str, Any],
) -> dict[str, Any]:
    passed = {str(value).strip() for value in statistical.get("passed_route_keys", []) if str(value).strip()}
    selected_keys = [_route_key(route) for route in selected_routes if isinstance(route, dict) and _route_key(route)]
    qualified_keys = [route_key for route_key in selected_keys if route_key in passed]
    selected_strategies = _strategy_keys(selected_routes)
    qualified_strategies = _strategy_keys([route for route in selected_routes if _route_key(route) in passed])
    strategy_breakdown = _portfolio_strategy_breakdown(selected_routes, passed)
    route_metrics = _aggregate_route_metrics(selected_routes, passed)
    status = "pass" if selected_keys and selected_keys == qualified_keys and len(qualified_keys) >= 2 and len(qualified_strategies) >= 2 else "fail"
    reasons: list[str] = []
    if not selected_keys:
        reasons.append("no_selected_routes")
    if selected_keys and selected_keys != qualified_keys:
        reasons.append("contains_non_qualified_routes")
    if len(qualified_keys) < 2:
        reasons.append("qualified_route_count_lt_2")
    if len(qualified_strategies) < 2:
        reasons.append("qualified_strategy_count_lt_2")
    return {
        "status": status,
        "reasons": reasons,
        "selected_route_count": len(selected_keys),
        "qualified_route_count": len(qualified_keys),
        "missing_route_count": max(0, len(selected_keys) - len(qualified_keys)),
        "selected_strategy_count": len(selected_strategies),
        "qualified_strategy_count": len(qualified_strategies),
        "missing_strategy_count": max(0, len(selected_strategies) - len(qualified_strategies)),
        "selected_route_keys": selected_keys,
        "qualified_route_keys": qualified_keys,
        "selected_strategy_keys": selected_strategies,
        "qualified_strategy_keys": qualified_strategies,
        "strategy_breakdown": strategy_breakdown,
        "metrics": route_metrics,
        "passed_route_keys": sorted(passed),
    }


def _portfolio_strategy_breakdown(
    selected_routes: list[dict[str, Any]],
    passed: set[str],
) -> dict[str, dict[str, Any]]:
    breakdown: dict[str, dict[str, Any]] = {}
    for route in selected_routes:
        if not isinstance(route, dict):
            continue
        strategy = str(route.get("strategy", "")).strip()
        route_key = _route_key(route)
        if not strategy or not route_key:
            continue
        bucket = breakdown.setdefault(
            strategy,
            {
                "selected_route_count": 0,
                "qualified_route_count": 0,
                "selected_route_keys": [],
                "qualified_route_keys": [],
            },
        )
        bucket["selected_route_count"] += 1
        bucket["selected_route_keys"].append(route_key)
        if route_key in passed:
            bucket["qualified_route_count"] += 1
            bucket["qualified_route_keys"].append(route_key)
    return breakdown


def _portfolio_strategy_actions(portfolio: dict[str, Any]) -> dict[str, dict[str, Any]]:
    breakdown = portfolio.get("strategy_breakdown", {})
    if not isinstance(breakdown, dict):
        breakdown = {}
    actions: dict[str, dict[str, Any]] = {}
    for strategy, counts in breakdown.items():
        if not isinstance(counts, dict):
            continue
        selected_count = int(counts.get("selected_route_count", 0) or 0)
        qualified_count = int(counts.get("qualified_route_count", 0) or 0)
        recommendation = "bundle_pass" if selected_count == qualified_count and qualified_count > 0 else "bundle_review"
        actions[str(strategy)] = {
            "selected_route_count": selected_count,
            "qualified_route_count": qualified_count,
            "selected_route_keys": list(counts.get("selected_route_keys", [])) if isinstance(counts.get("selected_route_keys", []), list) else [],
            "qualified_route_keys": list(counts.get("qualified_route_keys", [])) if isinstance(counts.get("qualified_route_keys", []), list) else [],
            "recommendation": recommendation,
        }
    return actions


def _portfolio_strategy_priority_summary(
    portfolio: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    actions = portfolio.get("strategy_breakdown", {})
    if not isinstance(actions, dict):
        actions = {}
    summary: dict[str, dict[str, Any]] = {}
    for strategy, counts in actions.items():
        if not isinstance(counts, dict):
            continue
        summary[str(strategy)] = {
            "recommendation": (
                "bundle_pass"
                if int(counts.get("selected_route_count", 0) or 0) == int(counts.get("qualified_route_count", 0) or 0)
                and int(counts.get("qualified_route_count", 0) or 0) > 0
                else "bundle_review"
            ),
            "priority_route_keys": [],
        }
        qualified_keys = [str(value) for value in counts.get("qualified_route_keys", []) if str(value).strip()]
        selected_keys = [str(value) for value in counts.get("selected_route_keys", []) if str(value).strip()]
        selected_only_keys = [key for key in selected_keys if key not in qualified_keys]
        summary[str(strategy)]["priority_route_keys"] = qualified_keys + selected_only_keys
    return summary


def _portfolio_next_action_summary(
    portfolio: dict[str, Any],
    route_quality: dict[str, Any],
    strategy_actions: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    route_actions = route_quality.get("route_actions", [])
    if not isinstance(route_actions, list):
        route_actions = []
    strategy_counts = route_quality.get("strategy_counts", {})
    if not isinstance(strategy_counts, dict):
        strategy_counts = {}

    route_actions_by_strategy: dict[str, dict[str, list[str]]] = {}
    for action in route_actions:
        if not isinstance(action, dict):
            continue
        strategy = str(action.get("strategy", "")).strip()
        if not strategy:
            route_key = str(action.get("route_key", "")).strip()
            if ":" in route_key:
                strategy = route_key.split(":", 1)[0].strip()
        rec = str(action.get("recommendation", "")).strip()
        if not strategy or not rec:
            continue
        bucket = route_actions_by_strategy.setdefault(strategy, {"accumulate_oos": [], "drop_or_retune": []})
        if rec in bucket:
            route_key = str(action.get("route_key", "")).strip()
            if route_key:
                bucket[rec].append(route_key)

    summary: dict[str, dict[str, Any]] = {}
    breakdown = portfolio.get("strategy_breakdown", {})
    if not isinstance(breakdown, dict):
        breakdown = {}
    for strategy in breakdown.keys():
        counts = strategy_counts.get(strategy, {})
        if not isinstance(counts, dict):
            counts = {}
        action = strategy_actions.get(strategy, {})
        if not isinstance(action, dict):
            action = {}
        selected_route_keys = [str(value) for value in action.get("selected_route_keys", []) if str(value).strip()]
        qualified_route_keys = [str(value) for value in action.get("qualified_route_keys", []) if str(value).strip()]
        fallback_accumulate = list(qualified_route_keys)
        fallback_drop = [key for key in selected_route_keys if key not in qualified_route_keys]
        summary[strategy] = {
            "selected_route_count": int(action.get("selected_route_count", 0) or 0),
            "qualified_route_count": int(action.get("qualified_route_count", 0) or 0),
            "recommendation": str(action.get("recommendation", "bundle_review")),
            "sample_thin_count": int(counts.get("sample_thin", 0) or 0),
            "oos_quality_count": int(counts.get("oos_quality", 0) or 0),
            "accumulate_oos_route_keys": route_actions_by_strategy.get(strategy, {}).get("accumulate_oos", fallback_accumulate),
            "drop_or_retune_route_keys": route_actions_by_strategy.get(strategy, {}).get("drop_or_retune", fallback_drop),
        }
    return summary


def _portfolio_next_action_route_keys(
    portfolio_next_action_summary: dict[str, dict[str, Any]],
) -> list[str]:
    if not isinstance(portfolio_next_action_summary, dict):
        return []
    priority: list[str] = []
    for strategy_data in portfolio_next_action_summary.values():
        if not isinstance(strategy_data, dict):
            continue
        for key in strategy_data.get("accumulate_oos_route_keys", []):
            route_key = str(key).strip()
            if route_key and route_key not in priority:
                priority.append(route_key)
    for strategy_data in portfolio_next_action_summary.values():
        if not isinstance(strategy_data, dict):
            continue
        for key in strategy_data.get("drop_or_retune_route_keys", []):
            route_key = str(key).strip()
            if route_key and route_key not in priority:
                priority.append(route_key)
    return priority


def _portfolio_qualification_gap_summary(
    portfolio: dict[str, Any],
    portfolio_next_action_route_keys: list[str],
) -> dict[str, Any]:
    selected_route_count = int(portfolio.get("selected_route_count", 0) or 0)
    qualified_route_count = int(portfolio.get("qualified_route_count", 0) or 0)
    selected_strategy_count = int(portfolio.get("selected_strategy_count", 0) or 0)
    qualified_strategy_count = int(portfolio.get("qualified_strategy_count", 0) or 0)
    return {
        "required_route_count": 2,
        "required_strategy_count": 2,
        "selected_route_count": selected_route_count,
        "qualified_route_count": qualified_route_count,
        "missing_route_count": max(0, selected_route_count - qualified_route_count),
        "selected_strategy_count": selected_strategy_count,
        "qualified_strategy_count": qualified_strategy_count,
        "missing_strategy_count": max(0, selected_strategy_count - qualified_strategy_count),
        "status": str(portfolio.get("status", "unknown")),
        "reasons": list(portfolio.get("reasons", [])) if isinstance(portfolio.get("reasons", []), list) else [],
        "next_route_keys": list(portfolio_next_action_route_keys),
    }


def _portfolio_risk_audit(risk_eval_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not risk_eval_rows:
        return {
            "status": "missing",
            "reasons": ["risk_eval_unavailable"],
            "latest_timestamp": "",
            "symbol_count": 0,
            "risk_blocked_count": 0,
            "current_dd_pct": 0.0,
            "portfolio_exposure_pct": 0.0,
            "correlated_exposure_pct": 0.0,
            "vol_weighted_exposure_pct": 0.0,
            "risk_contribution_pct": 0.0,
        }
    latest_ts = max(str(row.get("timestamp", "")) for row in risk_eval_rows)
    latest_rows = [row for row in risk_eval_rows if str(row.get("timestamp", "")) == latest_ts]
    if not latest_rows:
        latest_rows = risk_eval_rows
        latest_ts = str(risk_eval_rows[-1].get("timestamp", ""))

    risk_blocked_count = sum(1 for row in latest_rows if bool(row.get("risk_blocked", False)))
    current_dd_pct = max(
        (float(row.get("current_dd_pct", 0.0) or 0.0) for row in latest_rows),
        default=0.0,
    )
    portfolio_exposure_pct = max(
        (float(row.get("portfolio_exposure_pct", 0.0) or 0.0) for row in latest_rows),
        default=0.0,
    )
    correlated_exposure_pct = max(
        (float(row.get("correlated_exposure_pct", 0.0) or 0.0) for row in latest_rows),
        default=0.0,
    )
    vol_weighted_exposure_pct = max(
        (float(row.get("vol_weighted_exposure_pct", 0.0) or 0.0) for row in latest_rows),
        default=0.0,
    )
    risk_contribution_pct = max(
        (float(row.get("risk_contribution_pct", 0.0) or 0.0) for row in latest_rows),
        default=0.0,
    )
    reasons: list[str] = []
    if risk_blocked_count:
        reasons.append("risk_blocked_rows_present")
    if current_dd_pct > 0.0 and current_dd_pct >= 15.0:
        reasons.append("dd_breach_or_limit")
    if correlated_exposure_pct >= 50.0:
        reasons.append("correlated_exposure_high")
    if vol_weighted_exposure_pct >= 60.0:
        reasons.append("vol_weighted_exposure_high")
    if risk_contribution_pct >= 55.0:
        reasons.append("risk_contribution_high")
    status = "pass" if not reasons else "warn"
    return {
        "status": status,
        "reasons": reasons,
        "latest_timestamp": latest_ts,
        "symbol_count": len({str(row.get("symbol", "")) for row in latest_rows if row.get("symbol")}),
        "risk_blocked_count": risk_blocked_count,
        "current_dd_pct": current_dd_pct,
        "portfolio_exposure_pct": portfolio_exposure_pct,
        "correlated_exposure_pct": correlated_exposure_pct,
        "vol_weighted_exposure_pct": vol_weighted_exposure_pct,
        "risk_contribution_pct": risk_contribution_pct,
    }


def _selection_bias_audit(
    selected_routes: list[dict[str, Any]],
    statistical: dict[str, Any],
    holdout_diff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    passed = {str(value).strip() for value in statistical.get("passed_route_keys", []) if str(value).strip()}
    selected_keys = [_route_key(route) for route in selected_routes if isinstance(route, dict) and _route_key(route)]
    qualified_keys = [route_key for route_key in selected_keys if route_key in passed]
    unqualified_keys = [route_key for route_key in selected_keys if route_key not in passed]
    holdout_audit = _final_holdout_audit(holdout_diff)
    holdout_required = holdout_diff is not None
    status = "pass" if selected_keys and not unqualified_keys and (not holdout_required or holdout_audit["status"] == "pass") else "warn"
    reasons: list[str] = []
    if not selected_keys:
        reasons.append("no_selected_routes")
    if unqualified_keys:
        reasons.append("selected_routes_not_in_passed_set")
    if holdout_required and holdout_audit["status"] != "pass":
        reasons.extend(holdout_audit.get("reasons", []))
    return {
        "status": status,
        "reasons": reasons,
        "selected_route_count": len(selected_keys),
        "passed_route_count": len(passed),
        "qualified_route_count": len(qualified_keys),
        "unqualified_route_count": len(unqualified_keys),
        "selected_route_keys": selected_keys,
        "passed_route_keys": sorted(passed),
        "qualified_route_keys": qualified_keys,
        "unqualified_route_keys": unqualified_keys,
        "final_holdout_audit": holdout_audit,
        "final_holdout_summary": _final_holdout_summary(holdout_audit),
    }


def _final_holdout_audit(holdout_diff: dict[str, Any] | None) -> dict[str, Any]:
    if not holdout_diff:
        return {
            "status": "missing",
            "reasons": ["manifest_vs_weekly_diff_unavailable"],
            "route_count": 0,
            "paired_route_count": 0,
            "route_deltas": [],
            "strategy_deltas": {},
        }
    rows = holdout_diff.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    route_deltas: list[dict[str, Any]] = []
    strategy_buckets: dict[str, list[dict[str, Any]]] = {}
    missing_source = 0
    missing_weekly = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = row.get("source", {})
        weekly = row.get("weekly", {})
        source_final = _extract_final_oos(source)
        weekly_final = _extract_final_oos(weekly)
        route_key = str(row.get("route_key", "")).strip()
        strategy = str(row.get("strategy", "")).strip()
        if not source_final:
            missing_source += 1
        if not weekly_final:
            missing_weekly += 1
        if source_final and weekly_final:
            delta = {
                "pf": float(weekly_final.get("pf", 0.0)) - float(source_final.get("pf", 0.0)),
                "expectancy_bps": float(weekly_final.get("expectancy_bps", 0.0)) - float(source_final.get("expectancy_bps", 0.0)),
                "period_pnl": float(weekly_final.get("period_pnl", 0.0)) - float(source_final.get("period_pnl", 0.0)),
                "max_dd": float(weekly_final.get("max_dd", 0.0)) - float(source_final.get("max_dd", 0.0)),
                "closed_trades": float(weekly_final.get("closed_trades", 0.0)) - float(source_final.get("closed_trades", 0.0)),
            }
            route_delta = {
                "route_key": route_key,
                "strategy": strategy,
                "source_final_oos": source_final,
                "weekly_final_oos": weekly_final,
                "delta": delta,
            }
            route_deltas.append(route_delta)
            if strategy:
                strategy_buckets.setdefault(strategy, []).append(route_delta)
    reasons: list[str] = []
    if missing_source:
        reasons.append("missing_source_final_oos")
    if missing_weekly:
        reasons.append("missing_weekly_final_oos")
    status = "pass" if not reasons and route_deltas else "warn"
    return {
        "status": status,
        "reasons": reasons,
        "route_count": len(rows),
        "paired_route_count": len(route_deltas),
        "route_deltas": route_deltas,
        "strategy_deltas": _final_holdout_strategy_summary(strategy_buckets),
    }


def _final_holdout_summary(holdout_audit: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(holdout_audit, dict):
        return {
            "status": "missing",
            "paired_route_count": 0,
            "avg_delta_pf": 0.0,
            "avg_delta_expectancy_bps": 0.0,
            "avg_delta_period_pnl": 0.0,
            "avg_delta_max_dd": 0.0,
            "avg_delta_closed_trades": 0.0,
            "strategy_summary": {},
        }
    route_deltas = holdout_audit.get("route_deltas", [])
    if not isinstance(route_deltas, list) or not route_deltas:
        return {
            "status": str(holdout_audit.get("status", "missing")),
            "paired_route_count": int(holdout_audit.get("paired_route_count", 0) or 0),
            "avg_delta_pf": 0.0,
            "avg_delta_expectancy_bps": 0.0,
            "avg_delta_period_pnl": 0.0,
            "avg_delta_max_dd": 0.0,
            "avg_delta_closed_trades": 0.0,
            "strategy_summary": {},
        }
    deltas = [delta for delta in (route_delta.get("delta", {}) for route_delta in route_deltas if isinstance(route_delta, dict)) if isinstance(delta, dict)]
    if not deltas:
        return {
            "status": str(holdout_audit.get("status", "missing")),
            "paired_route_count": int(holdout_audit.get("paired_route_count", 0) or 0),
            "avg_delta_pf": 0.0,
            "avg_delta_expectancy_bps": 0.0,
            "avg_delta_period_pnl": 0.0,
            "avg_delta_max_dd": 0.0,
            "avg_delta_closed_trades": 0.0,
        }
    return {
        "status": str(holdout_audit.get("status", "missing")),
        "paired_route_count": int(holdout_audit.get("paired_route_count", 0) or 0),
        "avg_delta_pf": _mean_dict(deltas, "pf"),
        "avg_delta_expectancy_bps": _mean_dict(deltas, "expectancy_bps"),
        "avg_delta_period_pnl": _mean_dict(deltas, "period_pnl"),
        "avg_delta_max_dd": _mean_dict(deltas, "max_dd"),
        "avg_delta_closed_trades": _mean_dict(deltas, "closed_trades"),
        "strategy_summary": holdout_audit.get("strategy_deltas", {}) if isinstance(holdout_audit.get("strategy_deltas", {}), dict) else {},
    }


def _final_holdout_strategy_summary(
    strategy_buckets: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for strategy, route_deltas in strategy_buckets.items():
        if not route_deltas:
            continue
        summary[str(strategy)] = {
            "route_count": len(route_deltas),
            "avg_delta_pf": _mean_dict([item.get("delta", {}) for item in route_deltas], "pf"),
            "avg_delta_expectancy_bps": _mean_dict([item.get("delta", {}) for item in route_deltas], "expectancy_bps"),
            "avg_delta_period_pnl": _mean_dict([item.get("delta", {}) for item in route_deltas], "period_pnl"),
            "avg_delta_max_dd": _mean_dict([item.get("delta", {}) for item in route_deltas], "max_dd"),
            "avg_delta_closed_trades": _mean_dict([item.get("delta", {}) for item in route_deltas], "closed_trades"),
        }
    return summary


def _extract_final_oos(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    final_oos = payload.get("final_oos", {})
    if isinstance(final_oos, dict) and final_oos:
        return final_oos
    fold_snapshot = payload.get("fold_snapshot", {})
    if isinstance(fold_snapshot, dict):
        nested = fold_snapshot.get("final_oos", {})
        if isinstance(nested, dict) and nested:
            return nested
    return {}


def _route_quality_audit(statistical: dict[str, Any]) -> dict[str, Any]:
    routes = statistical.get("routes", [])
    if not isinstance(routes, list) or not routes:
        return {
            "status": "missing",
            "reasons": ["statistical_routes_unavailable"],
            "sample_thin_route_count": 0,
            "oos_quality_route_count": 0,
            "sample_thin_route_keys": [],
            "oos_quality_route_keys": [],
            "route_actions": [],
        }
    sample_thin_reason_codes = {"min_route_trades", "min_strategy_trades"}
    sample_thin_route_keys: list[str] = []
    oos_quality_route_keys: list[str] = []
    route_actions: list[dict[str, Any]] = []
    strategy_counts: dict[str, dict[str, int]] = {}
    for row in routes:
        if not isinstance(row, dict):
            continue
        route_key = str(row.get("route_key", "")).strip()
        strategy = str(row.get("strategy", "")).strip()
        if not strategy and ":" in route_key:
            strategy = route_key.split(":", 1)[0].strip()
        if not route_key:
            continue
        route_reasons = {str(value).strip() for value in row.get("reasons", []) if str(value).strip()}
        if strategy:
            bucket = strategy_counts.setdefault(strategy, {"total": 0, "sample_thin": 0, "oos_quality": 0})
            bucket["total"] += 1
        if route_reasons & sample_thin_reason_codes:
            sample_thin_route_keys.append(route_key)
            if strategy:
                strategy_counts[strategy]["sample_thin"] += 1
            route_actions.append(
                {
                    "route_key": route_key,
                    "strategy": strategy,
                    "category": "sample_thin",
                    "recommendation": "accumulate_oos",
                    "reason_codes": sorted(route_reasons),
                }
            )
        elif str(row.get("status", "")).strip() == "fail":
            oos_quality_route_keys.append(route_key)
            if strategy:
                strategy_counts[strategy]["oos_quality"] += 1
            route_actions.append(
                {
                    "route_key": route_key,
                    "strategy": strategy,
                    "category": "oos_quality",
                    "recommendation": "drop_or_retune",
                    "reason_codes": sorted(route_reasons),
                }
            )
    summary_reasons: list[str] = []
    if sample_thin_route_keys:
        summary_reasons.append("sample_thin_routes_present")
    if oos_quality_route_keys:
        summary_reasons.append("oos_quality_routes_present")
    status = "pass" if not summary_reasons else "warn"
    return {
        "status": status,
        "reasons": summary_reasons,
        "sample_thin_route_count": len(sample_thin_route_keys),
        "oos_quality_route_count": len(oos_quality_route_keys),
        "sample_thin_route_keys": sample_thin_route_keys,
        "oos_quality_route_keys": oos_quality_route_keys,
        "route_actions": route_actions,
        "strategy_counts": strategy_counts,
    }


def _route_quality_summary(route_quality: dict[str, Any]) -> dict[str, Any]:
    actions = route_quality.get("route_actions", [])
    if not isinstance(actions, list):
        actions = []
    recommendations: dict[str, int] = {}
    categories: dict[str, int] = {}
    for action in actions:
        if not isinstance(action, dict):
            continue
        recommendation = str(action.get("recommendation", "")).strip()
        category = str(action.get("category", "")).strip()
        if recommendation:
            recommendations[recommendation] = recommendations.get(recommendation, 0) + 1
        if category:
            categories[category] = categories.get(category, 0) + 1
    return {
        "sample_thin_count": int(route_quality.get("sample_thin_route_count", 0) or 0),
        "oos_quality_count": int(route_quality.get("oos_quality_route_count", 0) or 0),
        "recommendations": recommendations,
        "categories": categories,
        "strategy_counts": route_quality.get("strategy_counts", {}),
    }


def _route_priority_summary(route_quality: dict[str, Any]) -> dict[str, Any]:
    actions = route_quality.get("route_actions", [])
    if not isinstance(actions, list):
        actions = []
    route_priority = {"accumulate_oos": 0, "drop_or_retune": 1}
    ordered = [
        {
            "route_key": str(action.get("route_key", "")),
            "category": str(action.get("category", "")),
            "recommendation": str(action.get("recommendation", "")),
            "reason_codes": list(action.get("reason_codes", [])) if isinstance(action.get("reason_codes", []), list) else [],
        }
        for action in actions
        if isinstance(action, dict) and str(action.get("route_key", "")).strip()
    ]
    ordered.sort(
        key=lambda item: (
            route_priority.get(str(item.get("recommendation", "")), 99),
            str(item.get("route_key", "")),
        )
    )
    return {
        "route_count": len(ordered),
        "priority_route_keys": [str(item.get("route_key", "")) for item in ordered],
        "route_actions": ordered,
    }


def _strategy_quality_summary(route_quality: dict[str, Any]) -> dict[str, Any]:
    strategy_counts = route_quality.get("strategy_counts", {})
    if not isinstance(strategy_counts, dict):
        strategy_counts = {}
    actions = route_quality.get("route_actions", [])
    if not isinstance(actions, list):
        actions = []

    summary: dict[str, dict[str, Any]] = {}
    for strategy, counts in strategy_counts.items():
        if not isinstance(counts, dict):
            continue
        total = int(counts.get("total", 0) or 0)
        sample_thin = int(counts.get("sample_thin", 0) or 0)
        oos_quality = int(counts.get("oos_quality", 0) or 0)
        if total == 0:
            rec = "monitor"
        elif oos_quality > 0:
            rec = "drop_or_retune"
        elif sample_thin > 0:
            rec = "accumulate_oos"
        else:
            rec = "monitor"
        summary[str(strategy)] = {
            "total": total,
            "sample_thin_count": sample_thin,
            "oos_quality_count": oos_quality,
            "recommendation": rec,
        }

    for action in actions:
        if not isinstance(action, dict):
            continue
        route_key = str(action.get("route_key", "")).strip()
        strategy = str(action.get("strategy", "")).strip()
        if not strategy and ":" in route_key:
            strategy = route_key.split(":", 1)[0].strip()
        if not strategy:
            continue
        summary.setdefault(
            strategy,
            {
                "total": 0,
                "sample_thin_count": 0,
                "oos_quality_count": 0,
                "recommendation": "monitor",
            },
        )
    return summary


def _strategy_keys(routes: list[dict[str, Any]]) -> list[str]:
    ordered: list[str] = []
    for route in routes:
        if not isinstance(route, dict):
            continue
        strategy = str(route.get("strategy", "")).strip()
        if strategy and strategy not in ordered:
            ordered.append(strategy)
    return ordered


def _mean_dict(rows: list[dict[str, Any]], key: str) -> float:
    vals = [float(row.get(key, 0.0)) for row in rows if isinstance(row, dict)]
    return sum(vals) / len(vals) if vals else 0.0


def _aggregate_route_metrics(
    routes: list[dict[str, Any]],
    passed: set[str],
) -> dict[str, float]:
    metrics = [cast(dict[str, Any], route.get("metrics", {})) for route in routes if isinstance(route, dict) and _route_key(route) in passed]
    if not metrics:
        return {
            "pf": 0.0,
            "expectancy_bps": 0.0,
            "period_pnl": 0.0,
            "max_drawdown": 0.0,
        }
    return {
        "pf": _mean_value(metrics, "pf"),
        "expectancy_bps": _mean_value(metrics, "expectancy_bps"),
        "period_pnl": _mean_value(metrics, "period_pnl"),
        "max_drawdown": _mean_value(metrics, "max_drawdown"),
    }


def _mean_value(rows: list[dict[str, Any]], key: str) -> float:
    vals = [float(row.get(key, 0.0)) for row in rows]
    return sum(vals) / len(vals) if vals else 0.0


def _route_key(route: dict[str, Any]) -> str:
    symbol = str(route.get("symbol", "")).strip().upper()
    timeframe = str(route.get("timeframe", "")).strip()
    strategy = str(route.get("strategy", "")).strip()
    if not symbol or not timeframe or not strategy:
        return ""
    return f"{strategy}:{symbol}:{timeframe}"


def _apply_statistical_to_candidate(candidate: dict[str, Any], statistical: dict[str, Any]) -> dict[str, Any]:
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
            route_key = f"{str(row.get('strategy', '')).strip()}:{str(row.get('symbol', '')).strip()}:{str(row.get('timeframe', '')).strip()}"
            row["statistical_status"] = "pass" if statistical_status == "pass" and route_key in passed else "fail"
            if row.get("candidate_status") == "core" and row["statistical_status"] != "pass":
                row["candidate_status"] = "watchlist"
            qualified_rows.append(row)
        out["rows"] = qualified_rows
    return out
