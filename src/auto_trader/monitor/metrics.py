from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from auto_trader.stateio import read_json_with_recovery


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = read_json_with_recovery(path)
    if isinstance(payload, dict):
        return payload
    return {}


def _latency_p95_ms(order_events_path: Path) -> float:
    if not order_events_path.exists():
        return 0.0
    rows: list[float] = []
    for line in order_events_path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        val = rec.get("latency_ms")
        if isinstance(val, int | float):
            rows.append(float(val))
    if not rows:
        return 0.0
    return float(pd.Series(rows).quantile(0.95))


def collect_runtime_metrics(
    *,
    runtime_state_path: str | Path = "data/runtime/control_state.json",
    gateway_state_path: str | Path = "data/exchange/gateway_state.json",
    risk_eval_path: str | Path = "data/risk/risk_eval.parquet",
    order_events_path: str | Path = "data/exchange/order_events.jsonl",
) -> dict[str, object]:
    runtime_state = _read_json(Path(runtime_state_path))
    gateway_state = _read_json(Path(gateway_state_path))

    trading_enabled = bool(runtime_state.get("trading_enabled", False))
    emergency_stop = bool(runtime_state.get("emergency_stop", False))
    pending_orders = gateway_state.get("pending_orders", {})
    backlog = 0
    if isinstance(pending_orders, dict):
        active_statuses = {"pending_submit", "retrying", "ack", "partial_filled"}
        for v in pending_orders.values():
            if not isinstance(v, dict):
                continue
            status = str(v.get("status", ""))
            if status in active_statuses:
                backlog += 1

    risk_rows = 0
    risk_block_count = 0
    risk_latest_dd = 0.0
    risk_latest_exposure = 0.0
    rp = Path(risk_eval_path)
    if rp.exists():
        try:
            risk_df = pd.read_parquet(rp)
            risk_rows = int(len(risk_df))
            if "blocked" in risk_df.columns:
                risk_block_count = int(
                    pd.to_numeric(risk_df["blocked"], errors="coerce").fillna(0).astype(bool).sum()
                )
            if "current_dd_pct" in risk_df.columns and not risk_df.empty:
                risk_latest_dd = float(
                    pd.to_numeric(risk_df["current_dd_pct"], errors="coerce").fillna(0.0).iloc[-1]
                )
            if "portfolio_exposure_pct" in risk_df.columns and not risk_df.empty:
                risk_latest_exposure = float(
                    pd.to_numeric(risk_df["portfolio_exposure_pct"], errors="coerce")
                    .fillna(0.0)
                    .iloc[-1]
                )
        except Exception:
            pass

    load1, _, _ = os.getloadavg()
    p95 = _latency_p95_ms(Path(order_events_path))
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "runtime_trading_enabled": trading_enabled,
        "runtime_emergency_stop": emergency_stop,
        "gateway_pending_orders": backlog,
        "order_latency_p95_ms": p95,
        "risk_rows": risk_rows,
        "risk_block_count": risk_block_count,
        "risk_latest_dd_pct": risk_latest_dd,
        "risk_latest_exposure_pct": risk_latest_exposure,
        "system_loadavg_1m": float(load1),
    }
