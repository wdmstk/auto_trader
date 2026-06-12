#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

DATA_ROOT="${DATA_ROOT:-data}"
ROUTES="${ROUTES:-}"
OUT_PATH="${OUT_PATH:-$DATA_ROOT/validation/trend_entry_diagnostics.md}"
JSON_OUT="${JSON_OUT:-${OUT_PATH%.md}.json}"
TREND_BREAKOUT_PERSISTENCE_MIN="${TREND_BREAKOUT_PERSISTENCE_MIN:-0.6}"
TREND_MOMENTUM_PERSISTENCE_MIN="${TREND_MOMENTUM_PERSISTENCE_MIN:-0.5}"
TREND_PULLBACK_SHALLOWNESS_MIN="${TREND_PULLBACK_SHALLOWNESS_MIN:-0.5}"
TREND_HIGHER_HIGH_PERSISTENCE_MIN="${TREND_HIGHER_HIGH_PERSISTENCE_MIN:-0.5}"
TREND_MIN_ENTRY_SCORE="${TREND_MIN_ENTRY_SCORE:-1.0}"

mkdir -p "$(dirname "$OUT_PATH")" "$(dirname "$JSON_OUT")"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python - "$DATA_ROOT" "$ROUTES" "$OUT_PATH" "$JSON_OUT" \
  "$TREND_BREAKOUT_PERSISTENCE_MIN" "$TREND_MOMENTUM_PERSISTENCE_MIN" \
  "$TREND_PULLBACK_SHALLOWNESS_MIN" "$TREND_HIGHER_HIGH_PERSISTENCE_MIN" \
  "$TREND_MIN_ENTRY_SCORE" <<'PY'
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

data_root = Path(sys.argv[1])
routes = [item.strip() for item in sys.argv[2].split(",") if item.strip()]
out_path = Path(sys.argv[3])
json_out = Path(sys.argv[4])
breakout_min = float(sys.argv[5])
momentum_min = float(sys.argv[6])
pullback_min = float(sys.argv[7])
higher_high_min = float(sys.argv[8])
min_entry_score = float(sys.argv[9])

if not routes:
    raise SystemExit("ROUTES is required")


def _load_route_data(symbol: str, timeframe: str) -> pd.DataFrame:
    features_path = data_root / "features" / f"{symbol}_{timeframe}_features.parquet"
    regime_path = data_root / "regime" / f"{symbol}_{timeframe}_regime.parquet"
    signals_path = data_root / "signals" / f"{symbol}_{timeframe}_trend_signals.parquet"
    if not features_path.exists():
        raise SystemExit(f"features not found: {features_path}")
    if not regime_path.exists():
        raise SystemExit(f"regime not found: {regime_path}")
    if not signals_path.exists():
        raise SystemExit(f"signals not found: {signals_path}")

    features = pd.read_parquet(features_path)
    regime = pd.read_parquet(regime_path)
    signals = pd.read_parquet(signals_path)
    for df in (features, regime, signals):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    merged = features.merge(regime, on=["symbol", "timeframe", "timestamp"], how="inner")
    merged = merged.merge(
        signals[
            [
                "symbol",
                "timeframe",
                "timestamp",
                "pass_filter",
                "entry_signal",
                "add_signal",
                "exit_signal",
                "signal_reason_codes",
            ]
        ],
        on=["symbol", "timeframe", "timestamp"],
        how="left",
    )
    return merged.sort_values("timestamp").reset_index(drop=True)


def _has_code(value: object, code: str) -> bool:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        return False
    return code in {str(item) for item in value}


def _analyze_route(route: str) -> dict[str, object]:
    strategy, symbol, timeframe = route.split(":", 2)
    if strategy != "trend":
        raise SystemExit(f"trend-only route expected: {route}")
    df = _load_route_data(symbol, timeframe)
    summary_path = data_root / "analysis" / f"walkforward_{symbol}_{timeframe}_trend_summary.parquet"
    trade_count = 0.0
    if summary_path.exists():
        sdf = pd.read_parquet(summary_path)
        if "closed_trades" in sdf.columns and not sdf.empty:
            trade_count = float(sdf["closed_trades"].sum())

    breakout_ok = df["breakout_persistence"].astype(float) >= breakout_min
    momentum_ok = df["momentum_persistence"].astype(float) >= momentum_min
    pullback_ok = df["pullback_shallowness"].astype(float) >= pullback_min
    higher_high_ok = df["higher_high_persistence"].astype(float) >= higher_high_min
    score = (
        breakout_ok.astype(int)
        + momentum_ok.astype(int)
        + pullback_ok.astype(int)
        + higher_high_ok.astype(int)
    ) / 4.0
    score_ok = score >= min_entry_score

    reason_series = df["signal_reason_codes"] if "signal_reason_codes" in df.columns else pd.Series([], dtype=object)
    cooldown_block = reason_series.apply(lambda value: _has_code(value, "TR_BLOCK_REENTRY_COOLDOWN"))
    disabled_block = reason_series.apply(lambda value: _has_code(value, "TR_BLOCK_SYMBOL_DISABLED"))
    risk_block = reason_series.apply(lambda value: _has_code(value, "TR_BLOCK_RISK_LIMIT"))
    high_vol_block = reason_series.apply(lambda value: _has_code(value, "TR_BLOCK_HIGH_VOL"))

    gate_open = df["pass_filter"].fillna(False).astype(bool)
    eligible = gate_open & ~cooldown_block & ~disabled_block
    non_entry_eligible = eligible & ~df["entry_signal"].fillna(False).astype(bool)

    fail_signature_counts: Counter[str] = Counter()
    for idx in df.index[non_entry_eligible]:
        failed_parts: list[str] = []
        if not bool(breakout_ok.loc[idx]):
            failed_parts.append("breakout")
        if not bool(momentum_ok.loc[idx]):
            failed_parts.append("momentum")
        if not bool(pullback_ok.loc[idx]):
            failed_parts.append("pullback")
        if not bool(higher_high_ok.loc[idx]):
            failed_parts.append("higher_high")
        if not failed_parts:
            failed_parts.append("other")
        fail_signature_counts["+".join(failed_parts)] += 1

    result = {
        "route": route,
        "rows": int(len(df)),
        "trade_count": trade_count,
        "entry_count": int(df["entry_signal"].fillna(False).astype(bool).sum()),
        "add_count": int(df["add_signal"].fillna(False).astype(bool).sum()),
        "exit_count": int(df["exit_signal"].fillna(False).astype(bool).sum()),
        "gate_open_rows": int(gate_open.sum()),
        "eligible_rows": int(eligible.sum()),
        "cooldown_block_rows": int(cooldown_block.sum()),
        "disabled_block_rows": int(disabled_block.sum()),
        "risk_block_rows": int(risk_block.sum()),
        "high_vol_block_rows": int(high_vol_block.sum()),
        "breakout_ok_rows": int(breakout_ok.sum()),
        "momentum_ok_rows": int(momentum_ok.sum()),
        "pullback_ok_rows": int(pullback_ok.sum()),
        "higher_high_ok_rows": int(higher_high_ok.sum()),
        "score_ok_rows": int(score_ok.sum()),
        "all_components_ok_rows": int((breakout_ok & momentum_ok & pullback_ok & higher_high_ok).sum()),
        "eligible_breakout_fail_rows": int((eligible & ~breakout_ok).sum()),
        "eligible_momentum_fail_rows": int((eligible & ~momentum_ok).sum()),
        "eligible_pullback_fail_rows": int((eligible & ~pullback_ok).sum()),
        "eligible_higher_high_fail_rows": int((eligible & ~higher_high_ok).sum()),
        "eligible_score_low_rows": int((eligible & ~score_ok).sum()),
        "eligible_non_entry_rows": int(non_entry_eligible.sum()),
        "eligible_failure_signatures": [
            {"signature": signature, "count": count}
            for signature, count in fail_signature_counts.most_common(8)
        ],
    }
    return result


results = [_analyze_route(route) for route in routes]
payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "data_root": str(data_root),
    "thresholds": {
        "breakout_persistence_min": breakout_min,
        "momentum_persistence_min": momentum_min,
        "pullback_shallowness_min": pullback_min,
        "higher_high_persistence_min": higher_high_min,
        "min_entry_score": min_entry_score,
    },
    "routes": results,
}
json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines = [
    "# Trend Entry Diagnostics",
    "",
    f"- generated_at: {payload['generated_at']}",
    f"- data_root: {data_root}",
    (
        "- thresholds: breakout>={breakout:.2f}, momentum>={momentum:.2f}, "
        "pullback>={pullback:.2f}, higher_high>={higher_high:.2f}, min_entry_score>={score:.2f}"
    ).format(
        breakout=breakout_min,
        momentum=momentum_min,
        pullback=pullback_min,
        higher_high=higher_high_min,
        score=min_entry_score,
    ),
    "",
    "| Route | Rows | Trades | Gate Open | Eligible | Entry | Add | Score OK | All4 OK |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for row in results:
    lines.append(
        "| {route} | {rows} | {trades:.2f} | {gate_open} | {eligible} | {entry} | {add} | {score_ok} | {all4_ok} |".format(
            route=str(row["route"]),
            rows=int(row["rows"]),
            trades=float(row["trade_count"]),
            gate_open=int(row["gate_open_rows"]),
            eligible=int(row["eligible_rows"]),
            entry=int(row["entry_count"]),
            add=int(row["add_count"]),
            score_ok=int(row["score_ok_rows"]),
            all4_ok=int(row["all_components_ok_rows"]),
        )
    )
lines.append("")

for row in results:
    eligible_rows = int(row["eligible_rows"])
    denom = float(eligible_rows) if eligible_rows > 0 else 1.0
    lines.append(f"## {row['route']}")
    lines.append("")
    lines.append(
        "- rows={rows} trades={trades:.2f} gate_open={gate_open} eligible={eligible} entry={entry} add={add} exit={exit}".format(
            rows=int(row["rows"]),
            trades=float(row["trade_count"]),
            gate_open=int(row["gate_open_rows"]),
            eligible=eligible_rows,
            entry=int(row["entry_count"]),
            add=int(row["add_count"]),
            exit=int(row["exit_count"]),
        )
    )
    lines.append(
        "- gate_blocks: high_vol={high_vol} risk={risk} cooldown={cooldown} disabled={disabled}".format(
            high_vol=int(row["high_vol_block_rows"]),
            risk=int(row["risk_block_rows"]),
            cooldown=int(row["cooldown_block_rows"]),
            disabled=int(row["disabled_block_rows"]),
        )
    )
    lines.append("")
    lines.append("| Metric | Count | Share of Eligible |")
    lines.append("|---|---:|---:|")
    for label, key in (
        ("Breakout Fail", "eligible_breakout_fail_rows"),
        ("Momentum Fail", "eligible_momentum_fail_rows"),
        ("Pullback Fail", "eligible_pullback_fail_rows"),
        ("Higher High Fail", "eligible_higher_high_fail_rows"),
        ("Score Low", "eligible_score_low_rows"),
        ("Non-Entry Eligible", "eligible_non_entry_rows"),
    ):
        count = int(row[key])
        lines.append(f"| {label} | {count} | {count / denom:.2%} |")
    lines.append("")
    lines.append("| Failure Signature | Count | Share of Eligible |")
    lines.append("|---|---:|---:|")
    signatures = row["eligible_failure_signatures"]
    if signatures:
        for item in signatures:
            count = int(item["count"])
            lines.append(f"| {item['signature']} | {count} | {count / denom:.2%} |")
    else:
        lines.append("| none | 0 | 0.00% |")
    lines.append("")

out_path.write_text("\n".join(lines), encoding="utf-8")
print(json_out)
print(out_path)
PY
