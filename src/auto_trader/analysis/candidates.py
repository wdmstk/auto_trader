from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
            "status": "warn",
        }

    for col in [
        "pf_mean",
        "expectancy_bps_mean",
        "period_pnl_mean",
        "max_dd_mean",
        "closed_trades_mean",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        else:
            df[col] = 0.0

    core_mask = (
        (df["pf_mean"] >= t.core_min_pf)
        & (df["expectancy_bps_mean"] > t.core_min_expectancy_bps)
        & (df["period_pnl_mean"] > t.core_min_period_pnl)
        & (df["max_dd_mean"] <= t.core_max_drawdown)
    )
    probe_mask = (
        ~core_mask
        & (df["closed_trades_mean"] >= t.min_closed_trades)
        & (df["pf_mean"] >= t.probe_min_pf)
        & (
            (df["expectancy_bps_mean"] > t.probe_min_expectancy_bps)
            | (df["period_pnl_mean"] > t.probe_min_period_pnl)
        )
        & (df["max_dd_mean"] <= t.probe_max_drawdown)
    )

    df["candidate_status"] = "watchlist"
    df.loc[probe_mask, "candidate_status"] = "probe"
    df.loc[core_mask, "candidate_status"] = "core"
    df["candidate_score"] = (
        df["expectancy_bps_mean"]
        + (10.0 * df["pf_mean"])
        + (2.0 * df["closed_trades_mean"].map(lambda v: float(v) ** 0.5))
        - (100.0 * df["max_dd_mean"])
    )
    df["candidate_priority"] = df["candidate_status"].map({"core": 0, "probe": 1, "watchlist": 2})

    sort_cols = [
        "candidate_priority",
        "candidate_score",
        "expectancy_bps_mean",
        "pf_mean",
        "closed_trades_mean",
    ]
    ascending = [True, False, False, False, False]
    ordered = df.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)

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

    return {
        "thresholds": t.__dict__,
        "rows": ordered.drop(columns=["candidate_priority"]).to_dict(orient="records"),
        "best_by_symbol_strategy": best_rows.drop(columns=["candidate_priority"]).to_dict(
            orient="records"
        ),
        "core_symbols": status_symbols["core"],
        "probe_symbols": status_symbols["probe"],
        "watchlist_symbols": status_symbols["watchlist"],
        "timeframes": _sort_timeframes(ordered["timeframe"].astype(str).unique().tolist())
        if "timeframe" in ordered.columns
        else [],
        "status": "pass" if not ordered.empty else "warn",
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
    if isinstance(summary, (str, Path)):
        payload = json.loads(Path(summary).read_text(encoding="utf-8"))
    else:
        payload = summary
    if isinstance(payload, dict):
        rows = payload.get("rows", [])
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    return []


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
