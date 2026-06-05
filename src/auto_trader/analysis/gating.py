from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class GatingThresholds:
    min_pf: float = 1.2
    min_expectancy_bps: float = 0.0
    min_period_pnl: float = 0.0
    max_drawdown: float = 0.08


def recommend_symbol_gating(
    summary: str | Path | dict[str, Any],
    *,
    timeframe: str = "15m",
    thresholds: GatingThresholds | None = None,
) -> dict[str, Any]:
    t = thresholds or GatingThresholds()
    rows = _load_rows(summary)
    df = pd.DataFrame(rows)
    if df.empty:
        return {
            "timeframe": timeframe,
            "thresholds": t.__dict__,
            "trend_enabled_symbols": [],
            "range_enabled_symbols": [],
            "trend_details": [],
            "range_details": [],
            "status": "warn",
        }

    if "timeframe" in df.columns:
        df = df[df["timeframe"].astype(str) == timeframe].copy()
    if df.empty:
        return {
            "timeframe": timeframe,
            "thresholds": t.__dict__,
            "trend_enabled_symbols": [],
            "range_enabled_symbols": [],
            "trend_details": [],
            "range_details": [],
            "status": "warn",
        }

    trend_details = _recommend_for_strategy(df, "trend", t)
    range_details = _recommend_for_strategy(df, "range", t)

    status = "pass" if trend_details["symbols"] or range_details["symbols"] else "warn"
    return {
        "timeframe": timeframe,
        "thresholds": t.__dict__,
        "trend_enabled_symbols": trend_details["symbols"],
        "range_enabled_symbols": range_details["symbols"],
        "trend_details": trend_details["details"],
        "range_details": range_details["details"],
        "status": status,
    }


def write_gating_artifacts(
    summary: str | Path | dict[str, Any],
    *,
    json_path: str | Path,
    env_path: str | Path | None = None,
    timeframe: str = "15m",
    thresholds: GatingThresholds | None = None,
) -> dict[str, Any]:
    recommendation = recommend_symbol_gating(
        summary,
        timeframe=timeframe,
        thresholds=thresholds,
    )
    json_out = Path(json_path)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(recommendation, ensure_ascii=True, indent=2), encoding="utf-8")

    if env_path is not None:
        env_out = Path(env_path)
        env_out.parent.mkdir(parents=True, exist_ok=True)
        env_out.write_text(
            "\n".join(
                [
                    f"TREND_ENABLED_SYMBOLS={','.join(recommendation['trend_enabled_symbols'])}",
                    f"RANGE_ENABLED_SYMBOLS={','.join(recommendation['range_enabled_symbols'])}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    return recommendation


def _recommend_for_strategy(
    df: pd.DataFrame,
    strategy: str,
    thresholds: GatingThresholds,
) -> dict[str, Any]:
    g = df[df["strategy"].astype(str) == strategy].copy()
    if g.empty:
        return {"symbols": [], "details": []}

    g["pf_mean"] = g["pf_mean"].astype(float)
    g["expectancy_bps_mean"] = g["expectancy_bps_mean"].astype(float)
    g["period_pnl_mean"] = g["period_pnl_mean"].astype(float)
    g["max_dd_mean"] = g["max_dd_mean"].astype(float)
    passing = g[
        (g["pf_mean"] >= thresholds.min_pf)
        & (g["expectancy_bps_mean"] > thresholds.min_expectancy_bps)
        & (g["period_pnl_mean"] > thresholds.min_period_pnl)
        & (g["max_dd_mean"] <= thresholds.max_drawdown)
    ].copy()
    if passing.empty:
        return {"symbols": [], "details": []}

    passing = passing.sort_values(
        ["expectancy_bps_mean", "pf_mean", "max_dd_mean", "period_pnl_mean"],
        ascending=[False, False, True, False],
    ).drop_duplicates(subset=["symbol"], keep="first")

    symbols = passing["symbol"].astype(str).tolist()
    details = [
        {
            "symbol": str(row.symbol),
            "timeframe": str(row.timeframe) if "timeframe" in passing.columns else "",
            "strategy": strategy,
            "pf_mean": float(row.pf_mean),
            "expectancy_bps_mean": float(row.expectancy_bps_mean),
            "period_pnl_mean": float(row.period_pnl_mean),
            "max_dd_mean": float(row.max_dd_mean),
        }
        for row in passing.itertuples(index=False)
    ]

    return {"symbols": symbols, "details": details}


def _load_rows(summary: str | Path | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(summary, (str, Path)):
        path = Path(summary)
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = summary
    if isinstance(payload, dict):
        rows = payload.get("rows", [])
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    return []
