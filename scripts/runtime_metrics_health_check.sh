#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

INPUT_PATH="${INPUT_PATH:-data/validation/runtime_metrics.jsonl}"
OUTPUT_DIR="${OUTPUT_DIR:-data/validation}"
OUTPUT_PATH="${OUTPUT_PATH:-$OUTPUT_DIR/runtime_metrics_health_report.json}"
RUN_ID="${RUN_ID:-${PIPELINE_RUN_ID:-}}"

PENDING_WARN="${PENDING_WARN:-3}"
PENDING_CRIT="${PENDING_CRIT:-10}"
LATENCY_WARN_MS="${LATENCY_WARN_MS:-500}"
LATENCY_CRIT_MS="${LATENCY_CRIT_MS:-2000}"
LOAD_WARN="${LOAD_WARN:-4.0}"
LOAD_CRIT="${LOAD_CRIT:-8.0}"
RISK_BLOCK_WARN="${RISK_BLOCK_WARN:-10}"

mkdir -p "$OUTPUT_DIR"

python - "$INPUT_PATH" "$OUTPUT_PATH" "$RUN_ID" \
  "$PENDING_WARN" "$PENDING_CRIT" \
  "$LATENCY_WARN_MS" "$LATENCY_CRIT_MS" \
  "$LOAD_WARN" "$LOAD_CRIT" \
  "$RISK_BLOCK_WARN" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def as_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def main() -> int:
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    run_id = sys.argv[3]
    pending_warn = float(sys.argv[4])
    pending_crit = float(sys.argv[5])
    latency_warn_ms = float(sys.argv[6])
    latency_crit_ms = float(sys.argv[7])
    load_warn = float(sys.argv[8])
    load_crit = float(sys.argv[9])
    risk_block_warn = float(sys.argv[10])
    generated_at = datetime.now(UTC).isoformat()

    if not input_path.exists():
        payload = {
            "run_id": run_id,
            "generated_at": generated_at,
            "overall_status": "fail",
            "reason": "input_missing",
            "input_path": str(input_path),
            "checked_at": generated_at,
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=True))
        return 1

    rows: list[dict[str, object]] = []
    for line in input_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            rows.append(rec)

    if not rows:
        payload = {
            "run_id": run_id,
            "generated_at": generated_at,
            "overall_status": "fail",
            "reason": "no_valid_rows",
            "input_path": str(input_path),
            "checked_at": generated_at,
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=True))
        return 1

    warn_count = 0
    crit_count = 0
    no_go_hits = 0
    disabled_hits = 0
    emergency_hits = 0

    max_pending = 0.0
    max_latency = 0.0
    max_load = 0.0
    max_blocks = 0.0

    for row in rows:
        pending = as_float(row.get("gateway_pending_orders", 0.0))
        latency = as_float(row.get("order_latency_p95_ms", 0.0))
        load1 = as_float(row.get("system_loadavg_1m", 0.0))
        blocks = as_float(row.get("risk_block_count", 0.0))
        trading_enabled = bool(row.get("runtime_trading_enabled", False))
        emergency = bool(row.get("runtime_emergency_stop", False))

        max_pending = max(max_pending, pending)
        max_latency = max(max_latency, latency)
        max_load = max(max_load, load1)
        max_blocks = max(max_blocks, blocks)

        warning = False
        critical = False
        if pending >= pending_crit:
            critical = True
            no_go_hits += 1
        elif pending >= pending_warn:
            warning = True
        if latency >= latency_crit_ms:
            critical = True
            no_go_hits += 1
        elif latency >= latency_warn_ms:
            warning = True
        if load1 >= load_crit:
            critical = True
            no_go_hits += 1
        elif load1 >= load_warn:
            warning = True
        if blocks >= risk_block_warn:
            warning = True
        if not trading_enabled:
            warning = True
            disabled_hits += 1
        if emergency:
            critical = True
            no_go_hits += 1
            emergency_hits += 1
        if critical:
            crit_count += 1
        elif warning:
            warn_count += 1

    overall = "pass"
    if no_go_hits > 0 or emergency_hits > 0:
        overall = "fail"
    elif warn_count > 0:
        overall = "warn"

    payload = {
        "run_id": run_id,
        "generated_at": generated_at,
        "overall_status": overall,
        "input_path": str(input_path),
        "output_path": str(output_path),
        "checked_at": generated_at,
        "rows": len(rows),
        "summary": {
            "warn_rows": warn_count,
            "critical_rows": crit_count,
            "no_go_hits": no_go_hits,
            "trading_disabled_rows": disabled_hits,
            "emergency_rows": emergency_hits,
        },
        "max_values": {
            "gateway_pending_orders": max_pending,
            "order_latency_p95_ms": max_latency,
            "system_loadavg_1m": max_load,
            "risk_block_count": max_blocks,
        },
        "thresholds": {
            "pending_warn": pending_warn,
            "pending_crit": pending_crit,
            "latency_warn_ms": latency_warn_ms,
            "latency_crit_ms": latency_crit_ms,
            "load_warn": load_warn,
            "load_crit": load_crit,
            "risk_block_warn": risk_block_warn,
        },
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=True))
    return 0 if overall in {"pass", "warn"} else 1


raise SystemExit(main())
PY

echo "report_path=$OUTPUT_PATH"
