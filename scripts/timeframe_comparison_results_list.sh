#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

SUMMARY_PATH="${SUMMARY_PATH:-data/validation/timeframe_eval/timeframe_comparison_summary.json}"
CANDIDATE_REPORT_PATH="${CANDIDATE_REPORT_PATH:-}"
OUT_PATH="${OUT_PATH:-$(dirname "$SUMMARY_PATH")/timeframe_comparison_result_list.md}"
DATA_ROOT="${DATA_ROOT:-data}"

mkdir -p "$(dirname "$OUT_PATH")"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
"$PYTHON_BIN" - "$SUMMARY_PATH" "$CANDIDATE_REPORT_PATH" "$OUT_PATH" "$DATA_ROOT" <<'PY'
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

summary_path = Path(sys.argv[1])
candidate_report_path = Path(sys.argv[2]) if sys.argv[2] else None
out_path = Path(sys.argv[3])
data_root = Path(sys.argv[4])

if not summary_path.exists():
    raise SystemExit(f"summary not found: {summary_path}")

summary = json.loads(summary_path.read_text(encoding="utf-8"))
rows = [row for row in summary.get("rows", []) if isinstance(row, dict)]
if not rows:
    raise SystemExit(f"no rows found: {summary_path}")

candidate_map: dict[tuple[str, str, str], str] = {}
candidate_score_map: dict[tuple[str, str, str], float] = {}
if candidate_report_path and candidate_report_path.exists():
    candidate_report = json.loads(candidate_report_path.read_text(encoding="utf-8"))
    for row in candidate_report.get("rows", []):
        if not isinstance(row, dict):
            continue
        key = (
            str(row.get("symbol", "")),
            str(row.get("strategy", "")),
            str(row.get("timeframe", "")),
        )
        candidate_map[key] = str(row.get("candidate_status", "-"))
        candidate_score_map[key] = float(row.get("candidate_score", 0.0) or 0.0)


def read_parquet_columns(path: Path, columns: list[str] | tuple[str, ...]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    parquet = pq.ParquetFile(path)
    available = [column for column in columns if column in parquet.schema_arrow.names]
    if not available:
        return pd.DataFrame()
    table = parquet.read(columns=available, use_threads=False)
    return table.to_pandas()


def normalize_reason_codes(value: object) -> list[str]:
    if value is None:
        return []
    codes = value.tolist() if hasattr(value, "tolist") else value
    if isinstance(codes, tuple):
        codes = list(codes)
    if isinstance(codes, list):
        return [str(code) for code in codes]
    return [str(codes)] if str(codes).strip() else []


def analyze_route_state(symbol: str, strategy: str, timeframe: str) -> dict[str, object]:
    signals_path = data_root / "signals" / f"{symbol}_{timeframe}_{strategy}_signals.parquet"
    summary_parquet_path = data_root / "analysis" / f"walkforward_{symbol}_{timeframe}_{strategy}_summary.parquet"
    out = {
        "gating": "unknown",
        "signal_count": 0,
        "trade_count": 0.0,
    }

    if signals_path.exists():
        df = read_parquet_columns(
            signals_path,
            ["entry_signal", "add_signal", "signal_reason_codes"],
        )
        signal_cols = [col for col in ("entry_signal", "add_signal") if col in df.columns]
        signal_count = 0
        if signal_cols:
            signal_mask = pd.Series(False, index=df.index)
            for col in signal_cols:
                signal_mask = signal_mask | df[col].fillna(False).astype(bool)
            signal_count = int(signal_mask.sum())
        out["signal_count"] = signal_count

        disabled_block_rows = 0
        if "signal_reason_codes" in df.columns:
            for value in df["signal_reason_codes"]:
                codes = normalize_reason_codes(value)
                if not codes:
                    continue
                if any(str(code).endswith("BLOCK_SYMBOL_DISABLED") for code in codes):
                    disabled_block_rows += 1
        if len(df) > 0 and disabled_block_rows == len(df):
            out["gating"] = "blocked"
        else:
            out["gating"] = "pass"

    if summary_parquet_path.exists():
        sdf = read_parquet_columns(summary_parquet_path, ["closed_trades"])
        if "closed_trades" in sdf.columns and not sdf.empty:
            out["trade_count"] = float(sdf["closed_trades"].sum())

    return out

timeframes = sorted({str(row.get("timeframe", "")) for row in rows})
status_counts: dict[str, int] = defaultdict(int)
for status in candidate_map.values():
    status_counts[status] += 1

lines: list[str] = []
lines.append("# Timeframe Comparison Result List")
lines.append("")
lines.append(f"- generated_at: {datetime.now(UTC).isoformat()}")
lines.append(f"- summary: {summary_path}")
if candidate_report_path:
    lines.append(f"- candidate_report: {candidate_report_path}")
lines.append(f"- timeframes: {', '.join(timeframes)}")
lines.append(f"- rows: {len(rows)}")
if status_counts:
    lines.append(
        "- candidate_status_counts: "
        + ", ".join(f"{key}={status_counts[key]}" for key in sorted(status_counts))
    )
lines.append("- gating: `blocked` は `signal_reason_codes` が全行 `*_BLOCK_SYMBOL_DISABLED` の route")
lines.append("- signal_0: `entry_signal` と `add_signal` の合計が 0")
lines.append("- trade_0: walkforward の `closed_trades` 合計が 0")
lines.append("")

for timeframe in timeframes:
    tf_rows = [row for row in rows if str(row.get("timeframe", "")) == timeframe]
    tf_rows.sort(
        key=lambda row: (
            str(row.get("strategy", "")),
            str(candidate_map.get((str(row.get("symbol", "")), str(row.get("strategy", "")), timeframe), "zzz")),
            -float(row.get("pf_mean", 0.0) or 0.0),
            -float(row.get("expectancy_bps_mean", 0.0) or 0.0),
            str(row.get("symbol", "")),
        )
    )
    lines.append(f"## {timeframe}")
    lines.append("")
    lines.append("| Strategy | Symbol | Candidate | Gating | Signal_0 | Trade_0 | Signal Count | Trade Count | PF | EXPbps | PeriodPnL | DD | Closed Trades | Score |")
    lines.append("|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in tf_rows:
        key = (
            str(row.get("symbol", "")),
            str(row.get("strategy", "")),
            str(row.get("timeframe", "")),
        )
        route_state = analyze_route_state(
            str(row.get("symbol", "")),
            str(row.get("strategy", "")),
            str(row.get("timeframe", "")),
        )
        signal_count = int(route_state["signal_count"])
        trade_count = float(route_state["trade_count"])
        lines.append(
            "| {strategy} | {symbol} | {status} | {gating} | {signal_0} | {trade_0} | {signal_count} | {trade_count:.2f} | {pf:.3f} | {exp:.2f} | {pnl:.3f} | {dd:.5f} | {trades:.2f} | {score:.2f} |".format(
                strategy=str(row.get("strategy", "")),
                symbol=str(row.get("symbol", "")),
                status=candidate_map.get(key, "-"),
                gating=str(route_state["gating"]),
                signal_0="yes" if signal_count == 0 else "no",
                trade_0="yes" if trade_count == 0 else "no",
                signal_count=signal_count,
                trade_count=trade_count,
                pf=float(row.get("pf_mean", 0.0) or 0.0),
                exp=float(row.get("expectancy_bps_mean", 0.0) or 0.0),
                pnl=float(row.get("period_pnl_mean", 0.0) or 0.0),
                dd=float(row.get("max_dd_mean", 0.0) or 0.0),
                trades=float(row.get("closed_trades_mean", 0.0) or 0.0),
                score=candidate_score_map.get(key, 0.0),
            )
        )
    lines.append("")

out_path.write_text("\n".join(lines), encoding="utf-8")
print(out_path)
PY
