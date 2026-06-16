#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "python interpreter not found" >&2
    exit 127
  fi
fi
DATA_ROOT="${DATA_ROOT:-data}"
TIMEFRAME="${TIMEFRAME:-1m}"
SYMBOLS="${SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT,ADAUSDT,SUIUSDT,TAOUSDT,ENAUSDT}"
OUT_PATH="${OUT_PATH:-$DATA_ROOT/validation/ohlcv_coverage_${TIMEFRAME}.md}"
GAP_OUT_PATH="${GAP_OUT_PATH:-$DATA_ROOT/validation/ohlcv_gaps_${TIMEFRAME}.md}"
GAP_WARN_MINUTES="${GAP_WARN_MINUTES:-5}"

mkdir -p "$(dirname "$OUT_PATH")"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
"$PYTHON_BIN" - "$DATA_ROOT" "$TIMEFRAME" "$SYMBOLS" "$OUT_PATH" "$GAP_OUT_PATH" "$GAP_WARN_MINUTES" <<'PY'
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

data_root = Path(sys.argv[1])
timeframe = str(sys.argv[2]).strip()
symbols = [item.strip() for item in str(sys.argv[3]).split(",") if item.strip()]
out_path = Path(sys.argv[4])
gap_out_path = Path(sys.argv[5])
gap_warn_minutes = float(sys.argv[6])

lines: list[str] = []
gap_lines: list[str] = []
lines.append("# OHLCV Coverage Check")
lines.append("")
lines.append(f"- generated_at: {datetime.now(UTC).isoformat()}")
lines.append(f"- timeframe: {timeframe}")
lines.append(f"- gap_warn_minutes: {gap_warn_minutes}")
lines.append("")
lines.append(
    "| Symbol | Rows | Start | End | Span Days | Median Gap Min | Max Gap Min | Gaps > Warn | Status |"
)
lines.append("|---|---:|---|---|---:|---:|---:|---:|---|")

gap_lines.append("# OHLCV Gap Detail")
gap_lines.append("")
gap_lines.append(f"- generated_at: {datetime.now(UTC).isoformat()}")
gap_lines.append(f"- timeframe: {timeframe}")
gap_lines.append(f"- gap_warn_minutes: {gap_warn_minutes}")
gap_lines.append("")
gap_lines.append("| Symbol | Gap Start | Gap End | Gap Minutes | Missing Bars Approx |")
gap_lines.append("|---|---|---|---:|---:|")

for symbol in symbols:
    path = data_root / "parquet" / f"{symbol}_{timeframe}.parquet"
    if not path.exists():
        lines.append(f"| {symbol} | 0 | - | - | 0.00 | - | - | - | missing |")
        continue

    frame = pd.read_parquet(path, columns=["timestamp"])
    if frame.empty:
        lines.append(f"| {symbol} | 0 | - | - | 0.00 | - | - | - | empty |")
        continue

    ts = pd.to_datetime(frame["timestamp"], utc=True).sort_values().reset_index(drop=True)
    start = ts.iloc[0]
    end = ts.iloc[-1]
    span_days = (end - start).total_seconds() / 86_400.0

    if len(ts) <= 1:
        median_gap = 0.0
        max_gap = 0.0
        gap_count = 0
    else:
        gaps = ts.diff().dropna().dt.total_seconds() / 60.0
        median_gap = float(gaps.median())
        max_gap = float(gaps.max())
        gap_count = int((gaps > gap_warn_minutes).sum())
        gap_rows = ts.to_frame(name="timestamp")
        gap_rows["prev_timestamp"] = gap_rows["timestamp"].shift(1)
        gap_rows["gap_minutes"] = (
            gap_rows["timestamp"] - gap_rows["prev_timestamp"]
        ).dt.total_seconds() / 60.0
        gap_rows = gap_rows[gap_rows["gap_minutes"] > gap_warn_minutes].copy()
        for _, gap_row in gap_rows.iterrows():
            prev_ts = gap_row["prev_timestamp"]
            curr_ts = gap_row["timestamp"]
            if pd.isna(prev_ts) or pd.isna(curr_ts):
                continue
            gap_minutes = float(gap_row["gap_minutes"])
            missing_bars = max(int(round(gap_minutes)) - 1, 0)
            gap_lines.append(
                "| {symbol} | {start} | {end} | {minutes:.2f} | {missing} |".format(
                    symbol=symbol,
                    start=pd.Timestamp(prev_ts).isoformat(),
                    end=pd.Timestamp(curr_ts).isoformat(),
                    minutes=gap_minutes,
                    missing=missing_bars,
                )
            )

    status = "ok"
    if gap_count > 0:
        status = "gap_warn"
    if span_days < 30.0:
        status = "short_window" if status == "ok" else f"{status}+short_window"

    lines.append(
        "| {symbol} | {rows} | {start} | {end} | {span:.2f} | {median:.2f} | {max_gap:.2f} | {gap_count} | {status} |".format(
            symbol=symbol,
            rows=len(ts),
            start=start.isoformat(),
            end=end.isoformat(),
            span=span_days,
            median=median_gap,
            max_gap=max_gap,
            gap_count=gap_count,
            status=status,
        )
    )

out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
gap_out_path.write_text("\n".join(gap_lines) + "\n", encoding="utf-8")
print(out_path)
print(gap_out_path)
PY
