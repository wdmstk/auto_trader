#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
MANIFEST_PATH="${MANIFEST_PATH:-data/validation/weekly_autotune/manifest/route_selection_manifest.json}"
WEEKLY_SUMMARY_PATH="${WEEKLY_SUMMARY_PATH:-data/validation/weekly_autotune/weekly_revalidation/manifest_route_summary.json}"
WEEKLY_CANDIDATE_PATH="${WEEKLY_CANDIDATE_PATH:-data/validation/weekly_autotune/weekly_revalidation/manifest_candidate_report.json}"
WEEKLY_REPORT_PATH="${WEEKLY_REPORT_PATH:-data/validation/weekly_autotune/weekly_revalidation/weekly_revalidation_report.json}"
STATISTICAL_REPORT_PATH="${STATISTICAL_REPORT_PATH:-data/validation/statistical_qualification/qualification_report.json}"
OUTPUT_JSON="${OUTPUT_JSON:-data/validation/weekly_autotune/weekly_revalidation/manifest_vs_weekly_diff.json}"
OUTPUT_MD="${OUTPUT_MD:-data/validation/weekly_autotune/weekly_revalidation/manifest_vs_weekly_diff.md}"
RUN_ID="${RUN_ID:-${PIPELINE_RUN_ID:-}}"

"$PYTHON_BIN" - "$MANIFEST_PATH" "$WEEKLY_SUMMARY_PATH" "$WEEKLY_CANDIDATE_PATH" "$WEEKLY_REPORT_PATH" "$STATISTICAL_REPORT_PATH" "$OUTPUT_JSON" "$OUTPUT_MD" "$RUN_ID" <<'PY'
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


def route_key(row: dict[str, object]) -> str:
    return f"{row.get('strategy','')}:{row.get('symbol','')}:{row.get('timeframe','')}"


def load_json(path_str: str) -> dict[str, object]:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def num(value: object) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def text(value: object) -> str:
    return str(value).strip()


def find_route_source(route_key: str, selected_stage: str, manifest_path: Path) -> dict[str, object]:
    run_root = manifest_path.parent.parent
    summary_paths = [
        run_root / "core_refinement" / "auto_tune_summary.json",
        run_root / "autotune_expansion" / "auto_tune_summary.json",
    ]
    for summary_path in summary_paths:
        if not summary_path.exists():
            continue
        payload = load_json(summary_path.as_posix())
        route_summaries = payload.get("route_summaries", [])
        if not isinstance(route_summaries, list):
            continue
        for item in route_summaries:
            if not isinstance(item, dict) or text(item.get("route", "")) != route_key:
                continue
            stages = item.get("stages", [])
            if not isinstance(stages, list):
                continue
            selected = item.get("selected", {})
            selected_config = ""
            if isinstance(selected, dict):
                selected_config = text(selected.get("config_label", ""))
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                if text(stage.get("stage", "")) != selected_stage:
                    continue
                summary_path_str = text(stage.get("summary_path", ""))
                summary_file = Path(summary_path_str) if summary_path_str else Path("")
                case_dir = (
                    summary_file.parent / "cases" / selected_config
                    if selected_config and summary_file
                    else Path("")
                )
                return {
                    "selection_mode": text(payload.get("selection_mode", "")),
                    "auto_tune_summary_path": summary_path.as_posix(),
                    "stage_summary_path": summary_path_str,
                    "case_dir": case_dir.as_posix() if case_dir else "",
                    "selected_config_label": selected_config,
                    "selected_metrics": selected if isinstance(selected, dict) else {},
                    "best_stage_metrics": stage.get("best", {}) if isinstance(stage.get("best", {}), dict) else {},
                }
    return {}


def load_fold_snapshot(analysis_dir: Path, symbol: str, timeframe: str, strategy: str) -> dict[str, object]:
    stamp = f"walkforward_{symbol}_{timeframe}_{strategy}"
    summary_path = analysis_dir / f"{stamp}_summary.parquet"
    closed_path = analysis_dir / f"{stamp}_closed_trades.parquet"
    if not summary_path.exists():
        return {}
    summary_df = pd.read_parquet(summary_path).sort_values("fold")
    folds = []
    for row in summary_df.to_dict("records"):
        folds.append(
            {
                "fold": int(num(row.get("fold", 0))),
                "closed_trades": num(row.get("closed_trades", 0.0)),
                "pf": num(row.get("pf", 0.0)),
                "expectancy_bps": num(row.get("expectancy_bps", 0.0)),
                "period_pnl": num(row.get("period_pnl", 0.0)),
                "max_dd": num(row.get("max_dd", 0.0)),
            }
        )
    final_fold = max((item["fold"] for item in folds), default=0)
    final_oos: dict[str, object] = {"fold": final_fold}
    if closed_path.exists():
        closed_df = pd.read_parquet(closed_path)
        if "fold" in closed_df.columns:
            oos_df = closed_df[closed_df["fold"] == final_fold].copy()
            if not oos_df.empty:
                entry_ts = pd.to_datetime(oos_df["entry_ts"], utc=True)
                exit_ts = pd.to_datetime(oos_df["exit_ts"], utc=True)
                final_oos.update(
                    {
                        "start": entry_ts.min().isoformat(),
                        "end": exit_ts.max().isoformat(),
                        "days": float((exit_ts.max() - entry_ts.min()).total_seconds() / 86400.0),
                        "closed_trades": float(len(oos_df)),
                    }
                )
    return {
        "summary_path": summary_path.as_posix(),
        "closed_trades_path": closed_path.as_posix() if closed_path.exists() else "",
        "folds": folds,
        "final_oos": final_oos,
    }


manifest = load_json(Path(__import__("sys").argv[1]).as_posix())
weekly_summary = load_json(Path(__import__("sys").argv[2]).as_posix())
weekly_candidate = load_json(Path(__import__("sys").argv[3]).as_posix())
weekly_report = load_json(Path(__import__("sys").argv[4]).as_posix())
statistical = load_json(Path(__import__("sys").argv[5]).as_posix())
output_json = Path(__import__("sys").argv[6])
output_md = Path(__import__("sys").argv[7])
manifest_path = Path(__import__("sys").argv[1])
run_id = __import__("sys").argv[8].strip()

manifest_routes = manifest.get("selection", {}).get("trade_routes", [])
manifest_routes = manifest_routes if isinstance(manifest_routes, list) else []
summary_rows = weekly_summary.get("rows", [])
summary_rows = summary_rows if isinstance(summary_rows, list) else []
candidate_rows = weekly_candidate.get("rows", [])
candidate_rows = candidate_rows if isinstance(candidate_rows, list) else []
selected_routes = weekly_report.get("selection", {}).get("trade_routes", [])
selected_routes = selected_routes if isinstance(selected_routes, list) else []
stat_routes = statistical.get("routes", [])
stat_routes = stat_routes if isinstance(stat_routes, list) else []

summary_by_key = {route_key(row): row for row in summary_rows if isinstance(row, dict)}
candidate_by_key = {route_key(row): row for row in candidate_rows if isinstance(row, dict)}
selected_by_key = {route_key(row): row for row in selected_routes if isinstance(row, dict)}
stat_by_key = {str(row.get("route_key", "")): row for row in stat_routes if isinstance(row, dict)}

rows: list[dict[str, object]] = []
for raw in manifest_routes:
    if not isinstance(raw, dict):
        continue
    key = route_key(raw)
    weekly_row = summary_by_key.get(key, {})
    candidate_row = candidate_by_key.get(key, {})
    selected_row = selected_by_key.get(key, {})
    stat_row = stat_by_key.get(key, {})
    source_info = find_route_source(key, text(raw.get("selected_stage", "")), manifest_path)
    source_case_dir = Path(text(source_info.get("case_dir", ""))) if text(source_info.get("case_dir", "")) else Path("")
    source_analysis_dir = source_case_dir / "run_data" / "analysis"
    source_fold_snapshot = (
        load_fold_snapshot(
            source_analysis_dir,
            text(raw.get("symbol", "")),
            text(raw.get("timeframe", "")),
            text(raw.get("strategy", "")),
        )
        if source_analysis_dir.exists()
        else {}
    )
    weekly_fold_snapshot = load_fold_snapshot(
        Path(text(weekly_report.get("summary_paths", {}).get("market", ""))).parent
        / "manifest_route_run_data"
        / "analysis",
        text(raw.get("symbol", "")),
        text(raw.get("timeframe", "")),
        text(raw.get("strategy", "")),
    )
    weekly_oos = stat_row.get("oos", {}) if isinstance(stat_row.get("oos", {}), dict) else {}
    weekly_final_oos = dict(
        weekly_fold_snapshot.get("final_oos", {})
        if isinstance(weekly_fold_snapshot, dict)
        else {}
    )
    if isinstance(weekly_oos, dict):
        weekly_final_oos.update({k: v for k, v in weekly_oos.items() if v is not None})
    rows.append(
        {
            "route_key": key,
            "strategy": raw.get("strategy", ""),
            "symbol": raw.get("symbol", ""),
            "timeframe": raw.get("timeframe", ""),
            "selected_stage": raw.get("selected_stage", ""),
            "params": raw.get("params", {}),
            "manifest": {
                "candidate_status": raw.get("candidate_status", ""),
                "statistical_status": raw.get("statistical_status", ""),
                "pf_mean": num(raw.get("pf_mean", 0.0)),
                "expectancy_bps_mean": num(raw.get("expectancy_bps_mean", 0.0)),
                "period_pnl_mean": num(raw.get("period_pnl_mean", 0.0)),
                "max_dd_mean": num(raw.get("max_dd_mean", 0.0)),
                "closed_trades_mean": num(raw.get("closed_trades_mean", 0.0)),
            },
            "source": {
                "selection_mode": text(source_info.get("selection_mode", "")),
                "auto_tune_summary_path": text(source_info.get("auto_tune_summary_path", "")),
                "stage_summary_path": text(source_info.get("stage_summary_path", "")),
                "case_dir": text(source_info.get("case_dir", "")),
                "config_label": text(source_info.get("selected_config_label", "")),
                "fold_snapshot": source_fold_snapshot,
            },
            "weekly": {
                "candidate_status": candidate_row.get("candidate_status", ""),
                "selected_in_weekly_report": bool(selected_row),
                "statistical_status": selected_row.get("statistical_status", stat_row.get("status", "")),
                "pf_mean": num(weekly_row.get("pf_mean", 0.0)),
                "expectancy_bps_mean": num(weekly_row.get("expectancy_bps_mean", 0.0)),
                "period_pnl_mean": num(weekly_row.get("period_pnl_mean", 0.0)),
                "max_dd_mean": num(weekly_row.get("max_dd_mean", 0.0)),
                "closed_trades_mean": num(weekly_row.get("closed_trades_mean", 0.0)),
                "statistical_reasons": stat_row.get("reasons", []),
                "fold_snapshot": weekly_fold_snapshot,
                "statistical_oos": weekly_final_oos,
            },
            "delta": {
                "pf_mean": num(weekly_row.get("pf_mean", 0.0)) - num(raw.get("pf_mean", 0.0)),
                "expectancy_bps_mean": num(weekly_row.get("expectancy_bps_mean", 0.0)) - num(raw.get("expectancy_bps_mean", 0.0)),
                "period_pnl_mean": num(weekly_row.get("period_pnl_mean", 0.0)) - num(raw.get("period_pnl_mean", 0.0)),
                "max_dd_mean": num(weekly_row.get("max_dd_mean", 0.0)) - num(raw.get("max_dd_mean", 0.0)),
                "closed_trades_mean": num(weekly_row.get("closed_trades_mean", 0.0)) - num(raw.get("closed_trades_mean", 0.0)),
            },
        }
    )

payload = {
    "run_id": run_id,
    "generated_at": datetime.now(UTC).isoformat(),
    "manifest_path": str(Path(__import__("sys").argv[1])),
    "weekly_summary_path": str(Path(__import__("sys").argv[2])),
    "weekly_candidate_path": str(Path(__import__("sys").argv[3])),
    "weekly_report_path": str(Path(__import__("sys").argv[4])),
    "statistical_report_path": str(Path(__import__("sys").argv[5])),
    "route_count": len(rows),
    "rows": rows,
}
output_json.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines = [
    "# Manifest vs Weekly Diff",
    "",
    f"- generated_at: {payload['generated_at']}",
    f"- run_id: {run_id or '-'}",
    f"- route_count: {len(rows)}",
    f"- manifest_path: {payload['manifest_path']}",
    f"- weekly_summary_path: {payload['weekly_summary_path']}",
    "",
    "| Route | Stage | Manifest PF | Weekly PF | dPF | Manifest EXPbps | Weekly EXPbps | dEXP | Manifest PnL | Weekly PnL | dPnL | Manifest Trades | Weekly Trades | dTrades | Weekly Candidate | Weekly Statistical | In Weekly Selection |",
    "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
]
for row in rows:
    m = row["manifest"]
    w = row["weekly"]
    d = row["delta"]
    lines.append(
        f"| {row['route_key']} | {row['selected_stage']} | "
        f"{m['pf_mean']:.3f} | {w['pf_mean']:.3f} | {d['pf_mean']:+.3f} | "
        f"{m['expectancy_bps_mean']:.2f} | {w['expectancy_bps_mean']:.2f} | {d['expectancy_bps_mean']:+.2f} | "
        f"{m['period_pnl_mean']:.3f} | {w['period_pnl_mean']:.3f} | {d['period_pnl_mean']:+.3f} | "
        f"{m['closed_trades_mean']:.2f} | {w['closed_trades_mean']:.2f} | {d['closed_trades_mean']:+.2f} | "
        f"{w['candidate_status']} | {w['statistical_status']} | {'yes' if w['selected_in_weekly_report'] else 'no'} |"
    )
lines.extend(["", "## Statistical Reasons", ""])
lines.extend(
    [
        "",
        "## Fold And OOS Drift",
        "",
        "| Route | Source Config | Source Final Fold | Source Trade OOS Days | Source Trade OOS Trades | Weekly Final Fold | Weekly Fold OOS Days | Weekly Trade OOS Days | Weekly Trade OOS Trades | dTrade OOS Days | dTrade OOS Trades | Source Stage Summary |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
)
for row in rows:
    source_snapshot = row["source"].get("fold_snapshot", {}) if isinstance(row.get("source"), dict) else {}
    weekly_snapshot = row["weekly"].get("fold_snapshot", {}) if isinstance(row.get("weekly"), dict) else {}
    source_oos = source_snapshot.get("final_oos", {}) if isinstance(source_snapshot, dict) else {}
    weekly_oos = row["weekly"].get("statistical_oos", {}) if isinstance(row.get("weekly"), dict) else {}
    source_days = num(source_oos.get("days", 0.0))
    weekly_days = num(weekly_oos.get("days", source_oos.get("days", 0.0)))
    weekly_trade_days = num(
        weekly_snapshot.get("final_oos", {}).get("days", 0.0)
        if isinstance(weekly_snapshot, dict)
        else 0.0
    )
    source_trades = num(source_oos.get("closed_trades", 0.0))
    weekly_trades = num(
        weekly_snapshot.get("final_oos", {}).get("closed_trades", 0.0)
        if isinstance(weekly_snapshot, dict)
        else 0.0
    )
    lines.append(
        f"| {row['route_key']} | {row['source'].get('config_label', '')} | "
        f"{int(num(source_oos.get('fold', 0)))} | {source_days:.2f} | {source_trades:.0f} | "
        f"{int(num(weekly_oos.get('fold', 0)))} | {weekly_days:.2f} | {weekly_trade_days:.2f} | {weekly_trades:.0f} | "
        f"{weekly_trade_days - source_days:+.2f} | {weekly_trades - source_trades:+.0f} | "
        f"{row['source'].get('stage_summary_path', '')} |"
    )
for row in rows:
    reasons = row["weekly"]["statistical_reasons"]
    lines.append(f"### {row['route_key']}")
    lines.append("")
    lines.append(f"- source_stage_summary_path: {row['source'].get('stage_summary_path', '-')}")
    lines.append(f"- source_case_dir: {row['source'].get('case_dir', '-')}")
    lines.append(f"- weekly_candidate_status: {row['weekly']['candidate_status']}")
    lines.append(f"- weekly_statistical_status: {row['weekly']['statistical_status']}")
    lines.append(f"- selected_in_weekly_report: {'yes' if row['weekly']['selected_in_weekly_report'] else 'no'}")
    lines.append(f"- reasons: {', '.join(str(x) for x in reasons) if reasons else '-'}")
    source_snapshot = row["source"].get("fold_snapshot", {}) if isinstance(row.get("source"), dict) else {}
    weekly_snapshot = row["weekly"].get("fold_snapshot", {}) if isinstance(row.get("weekly"), dict) else {}
    source_oos = source_snapshot.get("final_oos", {}) if isinstance(source_snapshot, dict) else {}
    weekly_oos = row["weekly"].get("statistical_oos", {}) if isinstance(row.get("weekly"), dict) else {}
    weekly_trade_oos = (
        weekly_snapshot.get("final_oos", {})
        if isinstance(weekly_snapshot, dict)
        else {}
    )
    lines.append(
        "- source_final_oos: fold={fold} start={start} end={end} days={days:.2f} trades={trades:.0f}".format(
            fold=int(num(source_oos.get("fold", 0))),
            start=text(source_oos.get("start", "-")) or "-",
            end=text(source_oos.get("end", "-")) or "-",
            days=num(source_oos.get("days", 0.0)),
            trades=num(source_oos.get("closed_trades", 0.0)),
        )
    )
    lines.append(
        "- weekly_final_oos: fold={fold} start={start} end={end} days={days:.2f} trades={trades:.0f}".format(
            fold=int(num(weekly_oos.get("fold", 0))),
            start=text(weekly_oos.get("start", "-")) or "-",
            end=text(weekly_oos.get("end", "-")) or "-",
            days=num(weekly_oos.get("days", 0.0)),
            trades=num(weekly_oos.get("closed_trades", 0.0)),
        )
    )
    lines.append(
        "- weekly_trade_oos: fold={fold} start={start} end={end} days={days:.2f} trades={trades:.0f}".format(
            fold=int(num(weekly_trade_oos.get("fold", 0))),
            start=text(weekly_trade_oos.get("start", "-")) or "-",
            end=text(weekly_trade_oos.get("end", "-")) or "-",
            days=num(weekly_trade_oos.get("days", 0.0)),
            trades=num(weekly_trade_oos.get("closed_trades", 0.0)),
        )
    )
    lines.append("")
    lines.append("| Fold | Source Trades | Source PF | Source EXPbps | Source PnL | Weekly Trades | Weekly PF | Weekly EXPbps | Weekly PnL |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    source_folds = {
        int(num(item.get("fold", 0))): item
        for item in source_snapshot.get("folds", [])
        if isinstance(item, dict)
    } if isinstance(source_snapshot, dict) else {}
    weekly_folds = {
        int(num(item.get("fold", 0))): item
        for item in weekly_snapshot.get("folds", [])
        if isinstance(item, dict)
    } if isinstance(weekly_snapshot, dict) else {}
    for fold in sorted(set(source_folds) | set(weekly_folds)):
        src = source_folds.get(fold, {})
        wk = weekly_folds.get(fold, {})
        lines.append(
            f"| {fold} | {num(src.get('closed_trades', 0.0)):.0f} | {num(src.get('pf', 0.0)):.3f} | "
            f"{num(src.get('expectancy_bps', 0.0)):.2f} | {num(src.get('period_pnl', 0.0)):.3f} | "
            f"{num(wk.get('closed_trades', 0.0)):.0f} | {num(wk.get('pf', 0.0)):.3f} | "
            f"{num(wk.get('expectancy_bps', 0.0)):.2f} | {num(wk.get('period_pnl', 0.0)):.3f} |"
        )
    lines.append("")

output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(output_json)
print(output_md)
PY
