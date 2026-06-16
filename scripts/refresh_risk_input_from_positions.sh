#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
POSITIONS_DIR="${POSITIONS_DIR:-data/positions}"
FEATURES_DIR="${FEATURES_DIR:-data/features}"
OUTPUT_PATH="${OUTPUT_PATH:-data/risk/risk_input.parquet}"
RISK_INPUT_EQUITY="${RISK_INPUT_EQUITY:-1000}"

echo "== refresh risk_input from positions =="
echo "positions=$POSITIONS_DIR features=$FEATURES_DIR output=$OUTPUT_PATH equity=$RISK_INPUT_EQUITY"

"$PYTHON_BIN" - "$POSITIONS_DIR" "$FEATURES_DIR" "$OUTPUT_PATH" "$RISK_INPUT_EQUITY" <<'PY'
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from auto_trader.position.store import PositionStore

positions_dir = Path(sys.argv[1])
features_dir = Path(sys.argv[2])
output_path = Path(sys.argv[3])
equity = float(sys.argv[4])
positions = PositionStore(positions_dir).load()

def _load_latest_volatility(features_dir: Path, symbol: str, timeframe: str) -> float:
    feature_path = features_dir / f"{symbol}_{timeframe}_features.parquet"
    if not feature_path.exists():
        return 0.0
    try:
        frame = pd.read_parquet(feature_path)
    except Exception:
        return 0.0
    if frame.empty:
        return 0.0
    if "timestamp" in frame.columns:
        frame = frame.sort_values("timestamp")
    for col in ("atr", "volatility", "rolling_volatility", "vol"):
        if col in frame.columns:
            series = pd.to_numeric(frame[col], errors="coerce").dropna()
            if not series.empty:
                return float(series.iloc[-1])
    return 0.0


rows: list[dict[str, object]] = []
now = datetime.now(UTC).isoformat()
columns = [
    "timestamp",
    "symbol",
    "current_equity",
    "equity_peak",
    "symbol_exposure_pct",
    "portfolio_exposure_pct",
    "concentration_score",
    "correlated_exposure_pct",
    "volatility",
]
if positions:
    notionals = {pos.symbol: abs(float(pos.qty) * float(pos.avg_entry)) for pos in positions}
    total_notional = sum(notionals.values())
    portfolio_exposure_pct = (total_notional / equity) * 100.0 if equity > 0 else 0.0
    top_two = sorted(notionals.values(), reverse=True)[:2]
    correlated_exposure_pct = (sum(top_two) / equity) * 100.0 if equity > 0 else 0.0
    concentration_score = (max(notionals.values()) / total_notional) if total_notional > 0 else 0.0
    for pos in positions:
        symbol_notional = notionals.get(pos.symbol, 0.0)
        volatility = _load_latest_volatility(features_dir, pos.symbol, pos.timeframe)
        rows.append(
            {
                "timestamp": now,
                "symbol": pos.symbol,
                "current_equity": equity,
                "equity_peak": equity,
                "symbol_exposure_pct": (symbol_notional / equity) * 100.0 if equity > 0 else 0.0,
                "portfolio_exposure_pct": portfolio_exposure_pct,
                "concentration_score": concentration_score,
                "correlated_exposure_pct": correlated_exposure_pct,
                "volatility": volatility,
            }
        )

output_path.parent.mkdir(parents=True, exist_ok=True)
pd.DataFrame(rows, columns=columns).to_parquet(output_path, index=False)
print(f"rows={len(rows)}")
PY
