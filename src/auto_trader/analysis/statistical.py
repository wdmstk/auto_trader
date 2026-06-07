from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StatisticalThresholds:
    min_route_trades: int = 30
    min_strategy_trades: int = 100
    min_oos_days: int = 30
    min_oos_ratio: float = 0.20
    min_pf: float = 1.2
    min_expectancy_bps: float = 0.0
    max_drawdown: float = 0.08
    min_pf_ci_lower: float = 1.0
    min_expectancy_bps_ci_lower: float = 0.0
    max_mc_drawdown_p95: float = 0.08
    max_mc_loss_probability: float = 0.05
    bootstrap_samples: int = 10_000
    block_size: int = 5
    seed: int = 29
    initial_cash: float = 10_000.0


def build_statistical_qualification(
    summary: str | Path | dict[str, Any],
    *,
    analysis_dir: str | Path,
    manifest_path: str | Path,
    report_path: str | Path | None = None,
    execution_delay_bars: int,
    ml_label_horizon_bars: int = 0,
    purge_bars: int = 0,
    thresholds: StatisticalThresholds | None = None,
) -> dict[str, Any]:
    t = thresholds or StatisticalThresholds()
    rows = _load_rows(summary)
    root = Path(analysis_dir)
    manifest_file = Path(manifest_path)
    inputs = _input_manifest(rows, root)
    settings = {
        "execution_delay_bars": execution_delay_bars,
        "ml_label_horizon_bars": ml_label_horizon_bars,
        "purge_bars": purge_bars,
        "thresholds": asdict(t),
    }
    current_manifest = {"schema_version": "1.0", "settings": settings, "inputs": inputs}
    manifest_status, manifest_reasons = _freeze_or_validate_manifest(
        manifest_file, current_manifest
    )

    route_results = [
        _qualify_route(row, root=root, thresholds=t)
        for row in rows
        if all(_route_fields(row)) and _is_point_candidate(row, t)
    ]
    strategy_results = [
        _qualify_strategy(strategy, route_results, thresholds=t) for strategy in ("trend", "range")
    ]
    audit_reasons = list(manifest_reasons)
    if execution_delay_bars < 1:
        audit_reasons.append("execution_delay_bars_lt_1")
    if purge_bars < ml_label_horizon_bars:
        audit_reasons.append("purge_bars_lt_ml_label_horizon")
    leakage_status = "pass" if not audit_reasons else "fail"
    route_pass = all(
        any(r["status"] == "pass" and r["strategy"] == strategy for r in route_results)
        for strategy in ("trend", "range")
    )
    strategy_pass = all(r["status"] == "pass" for r in strategy_results)
    status = (
        "pass"
        if manifest_status == "pass" and leakage_status == "pass" and route_pass and strategy_pass
        else "fail"
    )
    report = {
        "schema_version": "1.0",
        "status": status,
        "manifest_status": manifest_status,
        "manifest_path": str(manifest_file),
        "qualification_report_path": str(report_path) if report_path else "",
        "thresholds": asdict(t),
        "leakage_audit": {"status": leakage_status, "reasons": audit_reasons},
        "routes": route_results,
        "strategies": strategy_results,
        "passed_route_keys": [str(r["route_key"]) for r in route_results if r["status"] == "pass"],
    }
    if report_path is not None:
        out = Path(report_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return report


def _qualify_route(
    row: dict[str, Any], *, root: Path, thresholds: StatisticalThresholds
) -> dict[str, Any]:
    symbol, timeframe, strategy = _route_fields(row)
    route_key = f"{strategy}:{symbol}:{timeframe}"
    stamp = f"{symbol}_{timeframe}_{strategy}"
    closed_path = root / f"walkforward_{stamp}_closed_trades.parquet"
    portfolio_path = root / f"walkforward_{stamp}_portfolio.parquet"
    reasons: list[str] = []
    if not closed_path.exists():
        reasons.append("closed_trades_artifact_missing")
    if not portfolio_path.exists():
        reasons.append("portfolio_artifact_missing")
    if reasons:
        return _failed_route(route_key, symbol, timeframe, strategy, reasons, closed_path)

    closed = pd.read_parquet(closed_path)
    portfolio = pd.read_parquet(portfolio_path)
    if closed.empty or "fold" not in closed.columns:
        reasons.append("closed_trades_empty_or_fold_missing")
    if portfolio.empty or not {"fold", "timestamp", "drawdown"}.issubset(portfolio.columns):
        reasons.append("portfolio_empty_or_required_columns_missing")
    if reasons:
        return _failed_route(route_key, symbol, timeframe, strategy, reasons, closed_path)

    final_fold = int(pd.to_numeric(portfolio["fold"]).max())
    oos_portfolio = portfolio[pd.to_numeric(portfolio["fold"]) == final_fold].copy()
    prior_portfolio = portfolio[pd.to_numeric(portfolio["fold"]) < final_fold].copy()
    oos_closed = closed[pd.to_numeric(closed["fold"]) == final_fold].copy()
    all_ts = pd.to_datetime(portfolio["timestamp"], utc=True)
    oos_ts = pd.to_datetime(oos_portfolio["timestamp"], utc=True)
    prior_ts = pd.to_datetime(prior_portfolio["timestamp"], utc=True)
    total_seconds = max((all_ts.max() - all_ts.min()).total_seconds(), 0.0)
    oos_seconds = max((oos_ts.max() - oos_ts.min()).total_seconds(), 0.0)
    oos_days = oos_seconds / 86_400.0
    oos_ratio = oos_seconds / total_seconds if total_seconds > 0 else 0.0
    stats = _statistics(oos_closed, thresholds=thresholds)
    max_dd = float(pd.to_numeric(oos_portfolio["drawdown"]).max())
    period_pnl = float(stats["period_pnl"])
    checks = {
        "min_route_trades": int(stats["closed_trades"]) >= thresholds.min_route_trades,
        "min_oos_days": oos_days >= thresholds.min_oos_days,
        "min_oos_ratio": oos_ratio >= thresholds.min_oos_ratio,
        "oos_boundary_separated": prior_ts.empty or prior_ts.max() < oos_ts.min(),
        "pf": float(stats["pf"]) >= thresholds.min_pf,
        "expectancy_bps": float(stats["expectancy_bps"]) > thresholds.min_expectancy_bps,
        "period_pnl": period_pnl > 0.0,
        "max_drawdown": max_dd <= thresholds.max_drawdown,
        "pf_ci_lower": float(stats["pf_ci_lower"]) > thresholds.min_pf_ci_lower,
        "expectancy_bps_ci_lower": (
            float(stats["expectancy_bps_ci_lower"]) > thresholds.min_expectancy_bps_ci_lower
        ),
        "mc_drawdown_p95": (float(stats["mc_drawdown_p95"]) <= thresholds.max_mc_drawdown_p95),
        "mc_loss_probability": (
            float(stats["mc_loss_probability"]) <= thresholds.max_mc_loss_probability
        ),
    }
    reasons.extend(name for name, ok in checks.items() if not ok)
    return {
        "route_key": route_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": strategy,
        "status": "pass" if not reasons else "fail",
        "reasons": reasons,
        "checks": checks,
        "oos": {
            "fold": final_fold,
            "start": oos_ts.min().isoformat(),
            "end": oos_ts.max().isoformat(),
            "days": oos_days,
            "ratio": oos_ratio,
        },
        "metrics": {**stats, "max_drawdown": max_dd},
        "closed_trades_path": str(closed_path),
    }


def _qualify_strategy(
    strategy: str, routes: list[dict[str, Any]], *, thresholds: StatisticalThresholds
) -> dict[str, Any]:
    selected = [r for r in routes if r.get("strategy") == strategy and r.get("status") == "pass"]
    frames: list[pd.DataFrame] = []
    for route in selected:
        path = Path(str(route.get("closed_trades_path", "")))
        oos = cast(dict[str, Any], route.get("oos", {}))
        if not path.exists() or "fold" not in oos:
            continue
        frame = pd.read_parquet(path)
        if "fold" in frame.columns:
            frames.append(frame[pd.to_numeric(frame["fold"]) == int(oos["fold"])].copy())
    closed = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    stats = _statistics(closed, thresholds=thresholds)
    max_dd = max(
        (
            float(cast(dict[str, Any], route.get("metrics", {})).get("max_drawdown", 1.0))
            for route in selected
        ),
        default=1.0,
    )
    count = int(stats["closed_trades"])
    checks = {
        "min_strategy_trades": count >= thresholds.min_strategy_trades,
        "has_qualified_route": bool(selected),
        "pf": float(stats["pf"]) >= thresholds.min_pf,
        "expectancy_bps": float(stats["expectancy_bps"]) > thresholds.min_expectancy_bps,
        "period_pnl": float(stats["period_pnl"]) > 0.0,
        "max_drawdown": max_dd <= thresholds.max_drawdown,
        "pf_ci_lower": float(stats["pf_ci_lower"]) > thresholds.min_pf_ci_lower,
        "expectancy_bps_ci_lower": (
            float(stats["expectancy_bps_ci_lower"]) > thresholds.min_expectancy_bps_ci_lower
        ),
        "mc_drawdown_p95": (float(stats["mc_drawdown_p95"]) <= thresholds.max_mc_drawdown_p95),
        "mc_loss_probability": (
            float(stats["mc_loss_probability"]) <= thresholds.max_mc_loss_probability
        ),
    }
    return {
        "strategy": strategy,
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "closed_trades": count,
        "metrics": {**stats, "max_drawdown": max_dd},
        "route_keys": [str(route["route_key"]) for route in selected],
        "reasons": [name for name, ok in checks.items() if not ok],
    }


def _statistics(
    closed: pd.DataFrame, *, thresholds: StatisticalThresholds
) -> dict[str, float | int]:
    pnl = (
        pd.to_numeric(closed.get("pnl", pd.Series(dtype=float)), errors="coerce")
        .dropna()
        .to_numpy()
    )
    bps = (
        pd.to_numeric(closed.get("return_bps", pd.Series(dtype=float)), errors="coerce")
        .dropna()
        .to_numpy()
    )
    if len(pnl) == 0 or len(bps) != len(pnl):
        return {
            "closed_trades": int(len(pnl)),
            "pf": 0.0,
            "expectancy_bps": 0.0,
            "period_pnl": float(pnl.sum()),
            "pf_ci_lower": 0.0,
            "expectancy_bps_ci_lower": 0.0,
            "mc_drawdown_p95": 1.0,
            "mc_loss_probability": 1.0,
        }
    rng = np.random.default_rng(thresholds.seed)
    samples = _moving_block_samples(
        len(pnl), thresholds.bootstrap_samples, thresholds.block_size, rng
    )
    pnl_samples = pnl[samples]
    bps_samples = bps[samples]
    pf_samples = np.apply_along_axis(_profit_factor, 1, pnl_samples)
    expectation_samples = bps_samples.mean(axis=1)
    mc_drawdowns = np.apply_along_axis(
        _max_drawdown_from_pnl, 1, pnl_samples, thresholds.initial_cash
    )
    ending = pnl_samples.sum(axis=1)
    return {
        "closed_trades": int(len(pnl)),
        "pf": _profit_factor(pnl),
        "expectancy_bps": float(bps.mean()),
        "period_pnl": float(pnl.sum()),
        "pf_ci_lower": float(np.quantile(pf_samples, 0.025)),
        "expectancy_bps_ci_lower": float(np.quantile(expectation_samples, 0.025)),
        "mc_drawdown_p95": float(np.quantile(mc_drawdowns, 0.95)),
        "mc_loss_probability": float((ending < 0.0).mean()),
    }


def _moving_block_samples(
    size: int, samples: int, block_size: int, rng: np.random.Generator
) -> np.ndarray:
    block = max(1, min(block_size, size))
    blocks = int(np.ceil(size / block))
    starts = rng.integers(0, size, size=(samples, blocks))
    offsets = np.arange(block)
    return ((starts[:, :, None] + offsets) % size).reshape(samples, -1)[:, :size]


def _profit_factor(pnl: np.ndarray) -> float:
    profit = float(pnl[pnl > 0.0].sum())
    loss = float(-pnl[pnl < 0.0].sum())
    return profit / loss if loss > 0.0 else (100.0 if profit > 0.0 else 0.0)


def _max_drawdown_from_pnl(pnl: np.ndarray, initial_cash: float) -> float:
    equity = initial_cash + np.cumsum(pnl)
    equity = np.concatenate(([initial_cash], equity))
    peaks = np.maximum.accumulate(equity)
    drawdowns = np.divide(peaks - equity, peaks, out=np.zeros_like(peaks), where=peaks > 0)
    return float(np.max(drawdowns))


def _input_manifest(rows: list[dict[str, Any]], root: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for row in rows:
        symbol, timeframe, strategy = _route_fields(row)
        if not symbol:
            continue
        stamp = f"{symbol}_{timeframe}_{strategy}"
        for suffix in ("closed_trades.parquet", "portfolio.parquet", "meta.json"):
            path = root / f"walkforward_{stamp}_{suffix}"
            entries.append({"path": str(path), "sha256": _sha256(path)})
    return entries


def _freeze_or_validate_manifest(path: Path, current: dict[str, Any]) -> tuple[str, list[str]]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, ensure_ascii=True, indent=2), encoding="utf-8")
        return "pass", []
    try:
        frozen = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "fail", ["frozen_manifest_invalid"]
    return ("pass", []) if frozen == current else ("fail", ["frozen_manifest_mismatch"])


def _sha256(path: Path) -> str:
    if not path.exists():
        return "missing"
    digest = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _failed_route(
    route_key: str,
    symbol: str,
    timeframe: str,
    strategy: str,
    reasons: list[str],
    closed_path: Path,
) -> dict[str, Any]:
    return {
        "route_key": route_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": strategy,
        "status": "fail",
        "reasons": reasons,
        "checks": {},
        "oos": {},
        "metrics": {"closed_trades": 0},
        "closed_trades_path": str(closed_path),
    }


def _route_fields(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("symbol", "")).strip(),
        str(row.get("timeframe", "")).strip(),
        str(row.get("strategy", "")).strip(),
    )


def _is_point_candidate(row: dict[str, Any], thresholds: StatisticalThresholds) -> bool:
    try:
        return (
            float(row.get("pf_mean", 0.0)) >= thresholds.min_pf
            and float(row.get("expectancy_bps_mean", 0.0)) > thresholds.min_expectancy_bps
            and float(row.get("period_pnl_mean", 0.0)) > 0.0
            and float(row.get("max_dd_mean", 1.0)) <= thresholds.max_drawdown
        )
    except (TypeError, ValueError):
        return False


def _load_rows(summary: str | Path | dict[str, Any]) -> list[dict[str, Any]]:
    payload: Any
    if isinstance(summary, str | Path):
        payload = json.loads(Path(summary).read_text(encoding="utf-8"))
    else:
        payload = summary
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)]
