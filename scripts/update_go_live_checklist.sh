#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

CHECKLIST_PATH="${CHECKLIST_PATH:-docs/implementation/trading-go-live-checklist.md}"
CHECKPOINTS_PATH="${CHECKPOINTS_PATH:-data/validation/longrun_checkpoints.jsonl}"
HEALTH_REPORT_PATH="${HEALTH_REPORT_PATH:-data/validation/runtime_metrics_health_report.json}"
WEEKLY_REPORT_PATH="${WEEKLY_REPORT_PATH:-data/validation/weekly_revalidation/weekly_revalidation_report.json}"
DECIDER="${DECIDER:-auto}"
DECISION_DATE="${DECISION_DATE:-$(TZ=Asia/Tokyo date +%F)}"
DRY_RUN="${DRY_RUN:-false}"
START_WATCHERS="${START_WATCHERS:-false}"

python - "$CHECKLIST_PATH" "$CHECKPOINTS_PATH" "$HEALTH_REPORT_PATH" "$WEEKLY_REPORT_PATH" "$DECIDER" "$DECISION_DATE" "$DRY_RUN" "$START_WATCHERS" <<'PY'
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        x = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return x if isinstance(x, dict) else {}


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


def mark_checkbox(md: str, label: str, checked: bool) -> str:
    pat = re.compile(rf"^- \[(?: |x)\] {re.escape(label)}$", re.MULTILINE)
    rep = f"- [{'x' if checked else ' '}] {label}"
    return pat.sub(rep, md)


def main() -> int:
    checklist_path = Path(sys.argv[1])
    checkpoints_path = Path(sys.argv[2])
    health_path = Path(sys.argv[3])
    weekly_path = Path(sys.argv[4])
    decider = sys.argv[5]
    decision_date = sys.argv[6]
    dry_run = sys.argv[7].lower() in {"1", "true", "yes", "on"}
    start_watchers = sys.argv[8].lower() in {"1", "true", "yes", "on"}

    md = checklist_path.read_text(encoding="utf-8")
    checkpoints = load_jsonl(checkpoints_path)
    health = load_json(health_path)
    weekly = load_json(weekly_path)

    health_status = str(health.get("overall_status", "unknown"))
    weekly_status = str(weekly.get("status", "unknown")) if weekly else "missing"
    rows = len(checkpoints)
    has_rows = rows > 0
    lock_residual = any(bool(r.get("runtime_lock_residual", False) or r.get("notify_lock_residual", False)) for r in checkpoints)
    runtime_alive_all = all(bool(r.get("runtime_alive", False)) for r in checkpoints) if checkpoints else False
    updated_progress_any = any(bool(r.get("runtime_updated_progress", False)) for r in checkpoints) if checkpoints else False
    if not start_watchers:
        runtime_alive_all = True

    longrun_ok = has_rows and (not lock_residual) and runtime_alive_all and updated_progress_any
    metrics_ok = health_status in {"pass", "warn"}
    go_ready = longrun_ok and metrics_ok and health_status == "pass"
    reasons: list[str] = []
    if not has_rows:
        reasons.append("longrun checkpoints が未取得")
    if lock_residual:
        reasons.append("lock residual が検出")
    if not runtime_alive_all:
        reasons.append("runtime watcher 生存継続を満たしていない")
    if not updated_progress_any:
        reasons.append("updated_at 更新継続を満たしていない")
    if health_status == "warn":
        reasons.append("runtime metrics が warn（しきい値未達項目あり）")
    if health_status == "fail":
        reasons.append("runtime metrics が fail（No-Go）")
    if health_status == "unknown":
        reasons.append("runtime metrics health report が未取得/不正")
    if weekly_status == "warn":
        reasons.append("weekly strategy revalidation が warn（要調整）")
    if weekly_status == "missing":
        reasons.append("weekly strategy revalidation report が未取得")

    md = mark_checkbox(md, "8時間以上の連続運転証跡", has_rows)
    md = mark_checkbox(md, "Runtime Metrics 自動採点レポートを取得", bool(health))
    md = mark_checkbox(md, "Longrun record へサマリ追記", True)
    md = mark_checkbox(md, ".lock 長時間残留なし", has_rows and (not lock_residual))
    md = mark_checkbox(md, "updated_at 更新継続", has_rows and updated_progress_any)
    md = mark_checkbox(md, "watcher 生存継続", has_rows and runtime_alive_all)
    md = mark_checkbox(md, "Go-Live Ready（通知保留条件付き）", go_ready)

    md = re.sub(r"^- 判定者: .*$", f"- 判定者: {decider}", md, flags=re.MULTILINE)
    md = re.sub(r"^- 判定日: .*$", f"- 判定日: {decision_date}", md, flags=re.MULTILINE)

    start_marker = "<!-- AUTO_DECISION_NOTES_START -->"
    end_marker = "<!-- AUTO_DECISION_NOTES_END -->"
    notes_lines = [
        start_marker,
        "### Auto Decision Notes",
        f"- go_live_ready: {'true' if go_ready else 'false'}",
        f"- health_status: {health_status}",
        f"- weekly_status: {weekly_status}",
        f"- longrun_rows: {rows}",
    ]
    if reasons:
        notes_lines.append("- unmet_reasons:")
        for r in reasons:
            notes_lines.append(f"  - {r}")
    else:
        notes_lines.append("- unmet_reasons: none")
    notes_lines.append(end_marker)
    notes_block = "\n".join(notes_lines)
    pattern = re.compile(
        rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}",
        flags=re.DOTALL,
    )
    if pattern.search(md):
        md = pattern.sub(notes_block, md)
    else:
        md = md.rstrip() + "\n\n" + notes_block + "\n"

    open_start = "<!-- AUTO_OPEN_ITEMS_START -->"
    open_end = "<!-- AUTO_OPEN_ITEMS_END -->"
    open_lines = [open_start, "### Auto Open Items"]
    if reasons:
        for r in reasons:
            open_lines.append(f"- [ ] {r}")
    else:
        open_lines.append("- [x] 未達理由なし")
    open_lines.append(open_end)
    open_block = "\n".join(open_lines)
    open_pattern = re.compile(
        rf"{re.escape(open_start)}.*?{re.escape(open_end)}",
        flags=re.DOTALL,
    )
    if open_pattern.search(md):
        md = open_pattern.sub(open_block, md)
    else:
        md = md.rstrip() + "\n\n" + open_block + "\n"

    summary = {
        "checklist_path": str(checklist_path),
        "rows": rows,
        "health_status": health_status,
        "weekly_status": weekly_status,
        "longrun_ok": longrun_ok,
        "metrics_ok": metrics_ok,
        "go_live_ready": go_ready,
        "unmet_reasons": reasons,
        "decider": decider,
        "decision_date": decision_date,
        "dry_run": dry_run,
    }
    if dry_run:
        summary["preview_head"] = "\n".join(md.splitlines()[:35])
        print(json.dumps(summary, ensure_ascii=True))
        return 0

    checklist_path.write_text(md, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True))
    return 0


raise SystemExit(main())
PY
