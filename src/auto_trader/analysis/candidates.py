from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pandas as pd


@dataclass(frozen=True)
class CandidateThresholds:
    core_min_pf: float = 1.2
    core_min_expectancy_bps: float = 0.0
    core_min_period_pnl: float = 0.0
    core_max_drawdown: float = 0.08
    probe_min_pf: float = 0.8
    probe_min_expectancy_bps: float = 0.0
    probe_min_period_pnl: float = 0.0
    probe_max_drawdown: float = 0.15
    min_closed_trades: float = 1.0


def recommend_symbol_candidates(
    summary: str | Path | dict[str, Any],
    *,
    thresholds: CandidateThresholds | None = None,
) -> dict[str, Any]:
    t = thresholds or CandidateThresholds()
    rows = _load_rows(summary)
    df = pd.DataFrame(rows)
    if df.empty:
        return {
            "thresholds": t.__dict__,
            "rows": [],
            "best_by_symbol_strategy": [],
            "core_symbols": [],
            "probe_symbols": [],
            "watchlist_symbols": [],
            "timeframes": [],
            "timeframe_reports": [],
            "shadow_routes_by_symbol": {},
            "route_counts": {"core": 0, "probe": 0, "watchlist": 0},
            "symbol_counts": {"core": 0, "probe": 0, "watchlist": 0},
            "candidate_counts": {"core": 0, "probe": 0, "watchlist": 0},
            "limit_metrics": _empty_limit_metrics(),
            "status": "warn",
        }

    df = _prepare_candidate_frame(df)
    global_report = _build_candidate_report(df, thresholds=t)
    timeframe_reports = [
        _build_candidate_report(df[df["timeframe"].astype(str) == timeframe].copy(), thresholds=t)
        | {"timeframe": timeframe}
        for timeframe in _sort_timeframes(df["timeframe"].astype(str).unique().tolist())
        if not df[df["timeframe"].astype(str) == timeframe].empty
    ]

    return {
        "thresholds": t.__dict__,
        **global_report,
        "timeframes": _sort_timeframes(df["timeframe"].astype(str).unique().tolist())
        if "timeframe" in df.columns
        else [],
        "timeframe_reports": timeframe_reports,
    }


def write_candidate_report(
    summary: str | Path | dict[str, Any],
    *,
    json_path: str | Path,
    thresholds: CandidateThresholds | None = None,
) -> dict[str, Any]:
    report = recommend_symbol_candidates(summary, thresholds=thresholds)
    out = Path(json_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return report


def _load_rows(summary: str | Path | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(summary, str | Path):
        payload = json.loads(Path(summary).read_text(encoding="utf-8"))
    else:
        payload = summary
    if isinstance(payload, dict):
        rows = payload.get("rows", [])
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    return []


def _prepare_candidate_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in [
        "pf_mean",
        "expectancy_bps_mean",
        "period_pnl_mean",
        "max_dd_mean",
        "closed_trades_mean",
    ]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
        else:
            out[col] = 0.0
    return out


def _build_candidate_report(
    df: pd.DataFrame,
    *,
    thresholds: CandidateThresholds,
) -> dict[str, Any]:
    if df.empty:
        return {
            "rows": [],
            "best_by_symbol_strategy": [],
            "core_symbols": [],
            "probe_symbols": [],
            "watchlist_symbols": [],
            "shadow_routes_by_symbol": {},
            "route_counts": {"core": 0, "probe": 0, "watchlist": 0},
            "symbol_counts": {"core": 0, "probe": 0, "watchlist": 0},
            "candidate_counts": {"core": 0, "probe": 0, "watchlist": 0},
            "limit_metrics": _empty_limit_metrics(),
            "status": "warn",
        }

    core_mask = (
        (df["pf_mean"] >= thresholds.core_min_pf)
        & (df["expectancy_bps_mean"] > thresholds.core_min_expectancy_bps)
        & (df["period_pnl_mean"] > thresholds.core_min_period_pnl)
        & (df["max_dd_mean"] <= thresholds.core_max_drawdown)
    )
    probe_mask = (
        ~core_mask
        & (df["closed_trades_mean"] >= thresholds.min_closed_trades)
        & (df["pf_mean"] >= thresholds.probe_min_pf)
        & (
            (df["expectancy_bps_mean"] > thresholds.probe_min_expectancy_bps)
            | (df["period_pnl_mean"] > thresholds.probe_min_period_pnl)
        )
        & (df["max_dd_mean"] <= thresholds.probe_max_drawdown)
    )

    working = df.copy()
    working["candidate_status"] = "watchlist"
    working.loc[probe_mask, "candidate_status"] = "probe"
    working.loc[core_mask, "candidate_status"] = "core"
    working["candidate_score"] = (
        working["expectancy_bps_mean"]
        + (10.0 * working["pf_mean"])
        + (2.0 * working["closed_trades_mean"].map(lambda v: float(v) ** 0.5))
        - (100.0 * working["max_dd_mean"])
    )
    working["candidate_priority"] = working["candidate_status"].map(
        {"core": 0, "probe": 1, "watchlist": 2}
    )

    ordered = working.sort_values(
        [
            "candidate_priority",
            "candidate_score",
            "expectancy_bps_mean",
            "pf_mean",
            "closed_trades_mean",
        ],
        ascending=[True, False, False, False, False],
    ).reset_index(drop=True)

    best_rows = (
        ordered.sort_values(
            [
                "symbol",
                "strategy",
                "candidate_priority",
                "candidate_score",
                "expectancy_bps_mean",
                "pf_mean",
            ],
            ascending=[True, True, True, False, False, False],
        )
        .drop_duplicates(subset=["symbol", "strategy"], keep="first")
        .sort_values(
            ["candidate_priority", "candidate_score", "expectancy_bps_mean", "pf_mean"],
            ascending=[True, False, False, False],
        )
        .reset_index(drop=True)
    )

    symbol_priority = ordered.groupby("symbol")["candidate_priority"].min()
    status_symbols = {
        "core": sorted(symbol_priority[symbol_priority == 0].index.astype(str).tolist()),
        "probe": sorted(symbol_priority[symbol_priority == 1].index.astype(str).tolist()),
        "watchlist": sorted(symbol_priority[symbol_priority == 2].index.astype(str).tolist()),
    }
    route_counts = {
        "core": int((working["candidate_status"] == "core").sum()),
        "probe": int((working["candidate_status"] == "probe").sum()),
        "watchlist": int((working["candidate_status"] == "watchlist").sum()),
    }
    symbol_counts = {
        "core": len(status_symbols["core"]),
        "probe": len(status_symbols["probe"]),
        "watchlist": len(status_symbols["watchlist"]),
    }
    shadow_routes_by_symbol = _shadow_routes_by_symbol(ordered)

    return {
        "rows": ordered.drop(columns=["candidate_priority"]).to_dict(orient="records"),
        "best_by_symbol_strategy": best_rows.drop(columns=["candidate_priority"]).to_dict(
            orient="records"
        ),
        "core_symbols": status_symbols["core"],
        "probe_symbols": status_symbols["probe"],
        "watchlist_symbols": status_symbols["watchlist"],
        "shadow_routes_by_symbol": shadow_routes_by_symbol,
        "route_counts": route_counts,
        "symbol_counts": symbol_counts,
        "candidate_counts": dict(route_counts),
        "limit_metrics": _limit_metrics_summary(ordered),
        "status": "pass" if not ordered.empty else "warn",
    }


def _sort_timeframes(timeframes: list[str]) -> list[str]:
    def key(value: str) -> tuple[int, str]:
        text = value.strip().lower()
        if text.endswith("m"):
            try:
                return (int(text[:-1]), text)
            except ValueError:
                return (10**9, text)
        if text.endswith("h"):
            try:
                return (int(text[:-1]) * 60, text)
            except ValueError:
                return (10**9, text)
        return (10**9, text)

    return sorted({str(v) for v in timeframes}, key=key)


def _limit_metrics_summary(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return _empty_limit_metrics()
    cols = [
        "limit_order_count_mean",
        "limit_filled_count_mean",
        "limit_partial_count_mean",
        "limit_expired_count_mean",
        "limit_canceled_count_mean",
        "limit_fill_rate_mean",
        "limit_maker_fill_rate_mean",
        "limit_taker_like_rate_mean",
    ]
    out: dict[str, float] = {}
    for col in cols:
        out[col] = (
            float(pd.to_numeric(df[col], errors="coerce").fillna(0.0).mean())
            if col in df.columns
            else 0.0
        )
    return out


def _empty_limit_metrics() -> dict[str, float]:
    return {
        "limit_order_count_mean": 0.0,
        "limit_filled_count_mean": 0.0,
        "limit_partial_count_mean": 0.0,
        "limit_expired_count_mean": 0.0,
        "limit_canceled_count_mean": 0.0,
        "limit_fill_rate_mean": 0.0,
        "limit_maker_fill_rate_mean": 0.0,
        "limit_taker_like_rate_mean": 0.0,
    }


def _shadow_routes_by_symbol(df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    shadows: dict[str, list[dict[str, Any]]] = {}
    if df.empty:
        return shadows
    ordered = df.sort_values(
        [
            "symbol",
            "candidate_priority",
            "candidate_score",
            "expectancy_bps_mean",
            "pf_mean",
            "timeframe",
            "strategy",
        ],
        ascending=[True, True, False, False, False, True, True],
    )
    for symbol, group in ordered.groupby("symbol", sort=True):
        rows = cast(
            list[dict[str, Any]],
            group.drop(columns=["candidate_priority"]).to_dict(orient="records"),
        )
        shadows[str(symbol)] = rows[1:] if len(rows) > 1 else []
    return shadows
