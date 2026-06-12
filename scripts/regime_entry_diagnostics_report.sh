#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

DATA_ROOT="${DATA_ROOT:-data}"
ROUTES="${ROUTES:-}"
OUT_PATH="${OUT_PATH:-$DATA_ROOT/validation/regime_entry_diagnostics.md}"
JSON_OUT="${JSON_OUT:-${OUT_PATH%.md}.json}"
TREND_BREAKOUT_PERSISTENCE_MIN="${TREND_BREAKOUT_PERSISTENCE_MIN:-0.6}"
TREND_MOMENTUM_PERSISTENCE_MIN="${TREND_MOMENTUM_PERSISTENCE_MIN:-0.5}"
TREND_PULLBACK_SHALLOWNESS_MIN="${TREND_PULLBACK_SHALLOWNESS_MIN:-0.5}"
TREND_HIGHER_HIGH_PERSISTENCE_MIN="${TREND_HIGHER_HIGH_PERSISTENCE_MIN:-0.5}"
TREND_MIN_ENTRY_SCORE="${TREND_MIN_ENTRY_SCORE:-1.0}"
REGIME_TREND_ADX_THRESHOLD="${REGIME_TREND_ADX_THRESHOLD:-25.0}"

mkdir -p "$(dirname "$OUT_PATH")" "$(dirname "$JSON_OUT")"

PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
python - "$DATA_ROOT" "$ROUTES" "$OUT_PATH" "$JSON_OUT" \
  "$TREND_BREAKOUT_PERSISTENCE_MIN" "$TREND_MOMENTUM_PERSISTENCE_MIN" \
  "$TREND_PULLBACK_SHALLOWNESS_MIN" "$TREND_HIGHER_HIGH_PERSISTENCE_MIN" \
  "$TREND_MIN_ENTRY_SCORE" "$REGIME_TREND_ADX_THRESHOLD" <<'PY'
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
adx_threshold = float(sys.argv[10])

if not routes:
    raise SystemExit("ROUTES is required")


def _load(symbol: str, timeframe: str, strategy: str) -> pd.DataFrame:
    features_path = data_root / "features" / f"{symbol}_{timeframe}_features.parquet"
    regime_path = data_root / "regime" / f"{symbol}_{timeframe}_regime.parquet"
    signals_path = data_root / "signals" / f"{symbol}_{timeframe}_{strategy}_signals.parquet"
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
                "exit_signal",
                "signal_reason_codes",
            ]
        ],
        on=["symbol", "timeframe", "timestamp"],
        how="left",
    )
    return merged.sort_values("timestamp").reset_index(drop=True)


def _safe_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _has_code(value: object, code: str) -> bool:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        return False
    return code in {str(item) for item in value}


def _analyze(route: str) -> dict[str, object]:
    strategy, symbol, timeframe = route.split(":")
    df = _load(symbol, timeframe, strategy)

    breakout = df["breakout_persistence"].astype(float)
    momentum = df["momentum_persistence"].astype(float)
    pullback = df["pullback_shallowness"].astype(float)
    higher_high = df["higher_high_persistence"].astype(float)
    trend_eff = df["trend_efficiency"].astype(float).abs()
    adx_proxy = (trend_eff * 100.0).clip(0, 50)

    breakout_ok = breakout >= breakout_min
    momentum_ok = momentum >= momentum_min
    pullback_ok = pullback >= pullback_min
    higher_high_ok = higher_high >= higher_high_min
    score = (
        breakout_ok.astype(int)
        + momentum_ok.astype(int)
        + pullback_ok.astype(int)
        + higher_high_ok.astype(int)
    ) / 4.0
    score_ok = score >= min_entry_score

    regime_trend_mask = (
        (df["breakout_persistence"].astype(float) >= 0.6)
        & (df["momentum_persistence"].astype(float) >= 0.5)
        & (adx_proxy >= adx_threshold)
    )
    actual_trend = df["regime"].astype(str) == "TREND"
    trade_allowed = df["is_trade_allowed"].fillna(False).astype(bool)
    gate_open = df["pass_filter"].fillna(False).astype(bool)
    entry_signal = df["entry_signal"].fillna(False).astype(bool)
    warmup = df["is_warmup"].fillna(False).astype(bool)

    reason_counts: Counter[str] = Counter()
    for value in df["reason_codes"] if "reason_codes" in df.columns else []:
        if hasattr(value, "tolist"):
            value = value.tolist()
        if not isinstance(value, (list, tuple)):
            continue
        for code in value:
            reason_counts[str(code)] += 1

    signal_reason_counts: Counter[str] = Counter()
    if "signal_reason_codes" in df.columns:
        for value in df["signal_reason_codes"]:
            if hasattr(value, "tolist"):
                value = value.tolist()
            if not isinstance(value, (list, tuple)):
                continue
            for code in value:
                signal_reason_counts[str(code)] += 1

    trend_mask_not_adopted = regime_trend_mask & (~actual_trend)
    entry_ready_not_entered = gate_open & score_ok & (~entry_signal)

    return {
        "route": route,
        "rows": int(len(df)),
        "warmup_rows": int(warmup.sum()),
        "trend_regime_rows": int(actual_trend.sum()),
        "range_regime_rows": int((df["regime"].astype(str) == "RANGE").sum()),
        "high_vol_regime_rows": int((df["regime"].astype(str) == "HIGH_VOL").sum()),
        "trade_allowed_rows": int(trade_allowed.sum()),
        "gate_open_rows": int(gate_open.sum()),
        "entry_rows": int(entry_signal.sum()),
        "regime_trend_mask_rows": int(regime_trend_mask.sum()),
        "trend_mask_not_adopted_rows": int(trend_mask_not_adopted.sum()),
        "score_ok_rows": int(score_ok.sum()),
        "entry_ready_not_entered_rows": int(entry_ready_not_entered.sum()),
        "breakout_ok_rows": int(breakout_ok.sum()),
        "momentum_ok_rows": int(momentum_ok.sum()),
        "pullback_ok_rows": int(pullback_ok.sum()),
        "higher_high_ok_rows": int(higher_high_ok.sum()),
        "adx_proxy_ge_threshold_rows": int((adx_proxy >= adx_threshold).sum()),
        "top_regime_reasons": [
            {"reason": reason, "count": count} for reason, count in reason_counts.most_common(8)
        ],
        "top_signal_reasons": [
            {"reason": reason, "count": count}
            for reason, count in signal_reason_counts.most_common(8)
        ],
        "trend_mask_blocked_by_reason": {
            "warmup": int((trend_mask_not_adopted & warmup).sum()),
            "high_vol": int(
                (trend_mask_not_adopted & (df["regime"].astype(str) == "HIGH_VOL")).sum()
            ),
            "trade_not_allowed": int((trend_mask_not_adopted & (~trade_allowed)).sum()),
        },
    }


results = [_analyze(route) for route in routes]
payload = {
    "generated_at": datetime.now(UTC).isoformat(),
    "data_root": str(data_root),
    "routes": results,
}
json_out.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

lines = [
    "# Regime Entry Diagnostics",
    "",
    f"- generated_at: {payload['generated_at']}",
    f"- data_root: {data_root}",
    (
        "- thresholds: regime_adx_proxy>={adx:.1f}, breakout>={breakout:.2f}, momentum>={momentum:.2f}, "
        "pullback>={pullback:.2f}, higher_high>={higher_high:.2f}, min_entry_score>={score:.2f}"
    ).format(
        adx=adx_threshold,
        breakout=breakout_min,
        momentum=momentum_min,
        pullback=pullback_min,
        higher_high=higher_high_min,
        score=min_entry_score,
    ),
    "",
]

for row in results:
    lines.append(f"## {row['route']}")
    lines.append("")
    lines.append(
        "- rows={rows} warmup={warmup} trend_regime={trend_regime} trade_allowed={trade_allowed} gate_open={gate_open} entries={entries}".format(
            rows=int(row["rows"]),
            warmup=int(row["warmup_rows"]),
            trend_regime=int(row["trend_regime_rows"]),
            trade_allowed=int(row["trade_allowed_rows"]),
            gate_open=int(row["gate_open_rows"]),
            entries=int(row["entry_rows"]),
        )
    )
    lines.append(
        "- regime_mask: trend_mask={trend_mask} trend_mask_not_adopted={not_adopted} adx_ok={adx_ok} breakout_ok={breakout_ok} momentum_ok={momentum_ok}".format(
            trend_mask=int(row["regime_trend_mask_rows"]),
            not_adopted=int(row["trend_mask_not_adopted_rows"]),
            adx_ok=int(row["adx_proxy_ge_threshold_rows"]),
            breakout_ok=int(row["breakout_ok_rows"]),
            momentum_ok=int(row["momentum_ok_rows"]),
        )
    )
    lines.append(
        "- entry_mask: score_ok={score_ok} entry_ready_not_entered={ready_not_entered} pullback_ok={pullback_ok} higher_high_ok={higher_high_ok}".format(
            score_ok=int(row["score_ok_rows"]),
            ready_not_entered=int(row["entry_ready_not_entered_rows"]),
            pullback_ok=int(row["pullback_ok_rows"]),
            higher_high_ok=int(row["higher_high_ok_rows"]),
        )
    )
    lines.append("")
    lines.append("| Top Regime Reasons | Count |")
    lines.append("|---|---:|")
    for item in row["top_regime_reasons"]:
        lines.append(f"| {item['reason']} | {int(item['count'])} |")
    lines.append("")
    lines.append("| Top Signal Reasons | Count |")
    lines.append("|---|---:|")
    for item in row["top_signal_reasons"]:
        lines.append(f"| {item['reason']} | {int(item['count'])} |")
    lines.append("")

out_path.write_text("\n".join(lines), encoding="utf-8")
print(json_out)
print(out_path)
PY
