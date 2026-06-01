#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -z "${RECORD_PATH:-}" ]]; then
  TODAY_JST="$(TZ=Asia/Tokyo date +%F)"
  RECORD_PATH="docs/implementation/longrun-validation-record-${TODAY_JST}.md"
fi
CHECKPOINTS_PATH="${CHECKPOINTS_PATH:-data/validation/longrun_checkpoints.jsonl}"
HEALTH_REPORT_PATH="${HEALTH_REPORT_PATH:-data/validation/runtime_metrics_health_report.json}"
FORCE_APPEND="${FORCE_APPEND:-false}"
DRY_RUN="${DRY_RUN:-false}"
OUTPUT_FORMAT="${OUTPUT_FORMAT:-json}"

python - "$RECORD_PATH" "$CHECKPOINTS_PATH" "$HEALTH_REPORT_PATH" "$FORCE_APPEND" "$DRY_RUN" "$OUTPUT_FORMAT" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    out: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        x = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return x if isinstance(x, dict) else {}


def pass_rate(rows: list[dict[str, object]], key: str, invert: bool = False) -> str:
    if not rows:
        return "n/a"
    ok = 0
    for row in rows:
        v = bool(row.get(key, False))
        if invert:
            v = not v
        if v:
            ok += 1
    return f"{ok}/{len(rows)}"


def main() -> int:
    record_path = Path(sys.argv[1])
    checkpoints_path = Path(sys.argv[2])
    health_path = Path(sys.argv[3])
    force_append = str(sys.argv[4]).lower() in {"1", "true", "yes", "on"}
    dry_run = str(sys.argv[5]).lower() in {"1", "true", "yes", "on"}
    output_format = str(sys.argv[6]).lower()
    rows = load_jsonl(checkpoints_path)
    health = load_json(health_path)

    now = datetime.now(UTC).isoformat()
    started = rows[0].get("checked_at", "n/a") if rows else "n/a"
    ended = rows[-1].get("checked_at", "n/a") if rows else "n/a"

    health_status = str(health.get("overall_status", "unknown"))
    no_go_hits = health.get("summary", {}).get("no_go_hits", "n/a") if isinstance(health.get("summary"), dict) else "n/a"

    window = f"{started} - {ended}"
    rows_count = len(rows)

    section = [
        "",
        "---",
        "",
        "## Auto Appended Longrun Summary",
        f"- generated_at: {now}",
        f"- checkpoints_window: {window}",
        f"- checkpoints_rows: {rows_count}",
        f"- runtime_updated_progress pass-rate: {pass_rate(rows, 'runtime_updated_progress')}",
        f"- notify_updated_progress pass-rate: {pass_rate(rows, 'notify_updated_progress')}",
        f"- runtime_lock_residual clear-rate: {pass_rate(rows, 'runtime_lock_residual', invert=True)}",
        f"- notify_lock_residual clear-rate: {pass_rate(rows, 'notify_lock_residual', invert=True)}",
        f"- runtime_alive pass-rate: {pass_rate(rows, 'runtime_alive')}",
        f"- notify_alive pass-rate: {pass_rate(rows, 'notify_alive')}",
        f"- ops_alive pass-rate: {pass_rate(rows, 'ops_alive')}",
        f"- runtime_metrics_health: {health_status}",
        f"- runtime_metrics_no_go_hits: {no_go_hits}",
        "",
        "### Evidence",
        f"- checkpoints: `{checkpoints_path}`",
        f"- runtime metrics health: `{health_path}`",
        "",
    ]

    record_path.parent.mkdir(parents=True, exist_ok=True)
    current = record_path.read_text(encoding="utf-8") if record_path.exists() else "# Longrun Validation Record\n"
    signature = f"- checkpoints_window: {window}\n- checkpoints_rows: {rows_count}"
    if output_format not in {"json", "markdown"}:
        output_format = "json"

    payload = {
        "record_path": str(record_path),
        "checkpoints_rows": rows_count,
        "runtime_metrics_health": health_status,
        "force_append": force_append,
        "dry_run": dry_run,
        "output_format": output_format,
    }

    if signature in current and not force_append:
        payload["skipped"] = True
        payload["reason"] = "duplicate_window_and_rows"
        if output_format == "markdown":
            print("\n".join(section))
        else:
            print(json.dumps(payload, ensure_ascii=True))
        return 0

    if dry_run:
        payload["preview"] = "\n".join(section)
        if output_format == "markdown":
            print(payload["preview"])
        else:
            print(json.dumps(payload, ensure_ascii=True))
        return 0

    record_path.write_text(current + "\n".join(section), encoding="utf-8")
    if output_format == "markdown":
        print("\n".join(section))
    else:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


raise SystemExit(main())
PY
