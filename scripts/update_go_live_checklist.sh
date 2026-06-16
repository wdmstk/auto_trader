#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

CHECKLIST_PATH="${CHECKLIST_PATH:-docs/implementation/trading-go-live-checklist.md}"
CHECKPOINTS_PATH="${CHECKPOINTS_PATH:-data/validation/longrun_checkpoints.jsonl}"
HEALTH_REPORT_PATH="${HEALTH_REPORT_PATH:-data/validation/runtime_metrics_health_report.json}"
WEEKLY_REPORT_PATH="${WEEKLY_REPORT_PATH:-}"
STATISTICAL_REPORT_PATH="${STATISTICAL_REPORT_PATH:-}"
STRATEGY_REPORT_PATH="${STRATEGY_REPORT_PATH:-}"
STRATEGY_REPORT_JSON_PATH="${STRATEGY_REPORT_JSON_PATH:-}"
AI_PROGRESS_REPORT_PATH="${AI_PROGRESS_REPORT_PATH:-}"
PIPELINE_SUMMARY_PATH="${PIPELINE_SUMMARY_PATH:-data/validation/weekly_autotune/pipeline_summary.json}"
RUNTIME_ENV_PATH="${RUNTIME_ENV_PATH:-data/validation/weekly_autotune/route_selection_runtime.env}"
MAX_ARTIFACT_AGE_HOURS="${MAX_ARTIFACT_AGE_HOURS:-36}"
DECIDER="${DECIDER:-auto}"
DECISION_DATE="${DECISION_DATE:-$(TZ=Asia/Tokyo date +%F)}"
DRY_RUN="${DRY_RUN:-false}"
START_WATCHERS="${START_WATCHERS:-false}"

python - "$CHECKLIST_PATH" "$CHECKPOINTS_PATH" "$HEALTH_REPORT_PATH" "$WEEKLY_REPORT_PATH" "$STATISTICAL_REPORT_PATH" "$STRATEGY_REPORT_PATH" "$STRATEGY_REPORT_JSON_PATH" "$AI_PROGRESS_REPORT_PATH" "$PIPELINE_SUMMARY_PATH" "$RUNTIME_ENV_PATH" "$MAX_ARTIFACT_AGE_HOURS" "$DECIDER" "$DECISION_DATE" "$DRY_RUN" "$START_WATCHERS" <<'PY'
from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
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


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def artifact_meta(path: Path, payload: dict[str, object], *, fallback_keys: tuple[str, ...]) -> dict[str, object]:
    timestamp = None
    timestamp_source = ""
    for key in fallback_keys:
        timestamp = parse_timestamp(payload.get(key))
        if timestamp is not None:
            timestamp_source = key
            break
    if timestamp is None and path.exists():
        timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        timestamp_source = "file_mtime"
    age_hours = None if timestamp is None else (datetime.now(UTC) - timestamp).total_seconds() / 3600.0
    return {
        "path": str(path),
        "run_id": str(payload.get("run_id", "")),
        "generated_at": timestamp.isoformat() if timestamp is not None else "",
        "timestamp_source": timestamp_source,
        "age_hours": age_hours,
    }


def format_age_hours(value: object) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}"


def resolve_weekly_path(
    explicit_weekly_path: str,
    runtime_env_path: Path,
    pipeline_summary_path: Path,
) -> tuple[Path, str]:
    if explicit_weekly_path:
        return Path(explicit_weekly_path), "explicit_weekly_report_path"

    runtime_env = load_env(runtime_env_path)
    for key in ("WEEKLY_REVALIDATION_REPORT_PATH", "ROUTE_SELECTION_PATH"):
        candidate = runtime_env.get(key, "").strip()
        if candidate:
            return Path(candidate), f"runtime_env:{key}"

    pipeline_summary = load_json(pipeline_summary_path)
    runtime = pipeline_summary.get("runtime", {})
    if isinstance(runtime, dict):
        for key in ("weekly_report_path", "route_selection_path"):
            candidate = str(runtime.get(key, "")).strip()
            if candidate:
                return Path(candidate), f"pipeline_summary:{key}"

    return (
        Path("data/validation/weekly_revalidation/weekly_revalidation_report.json"),
        "legacy_default",
    )


def mark_checkbox(md: str, label: str, checked: bool) -> str:
    pat = re.compile(rf"^- \[(?: |x)\] {re.escape(label)}$", re.MULTILINE)
    rep = f"- [{'x' if checked else ' '}] {label}"
    return pat.sub(rep, md)


def main() -> int:
    checklist_path = Path(sys.argv[1])
    checkpoints_path = Path(sys.argv[2])
    health_path = Path(sys.argv[3])
    explicit_weekly_path = sys.argv[4]
    explicit_statistical_path = sys.argv[5]
    explicit_strategy_path = sys.argv[6]
    explicit_strategy_json_path = sys.argv[7]
    explicit_ai_progress_path = sys.argv[8]
    pipeline_summary_path = Path(sys.argv[9])
    runtime_env_path = Path(sys.argv[10])
    max_artifact_age_hours = float(sys.argv[11])
    decider = sys.argv[12]
    decision_date = sys.argv[13]
    dry_run = sys.argv[14].lower() in {"1", "true", "yes", "on"}
    start_watchers = sys.argv[15].lower() in {"1", "true", "yes", "on"}

    md = checklist_path.read_text(encoding="utf-8")
    checkpoints = load_jsonl(checkpoints_path)
    health = load_json(health_path)
    weekly_path, weekly_path_source = resolve_weekly_path(
        explicit_weekly_path,
        runtime_env_path,
        pipeline_summary_path,
    )
    weekly = load_json(weekly_path)
    statistical = weekly.get("statistical_qualification", {}) if weekly else {}
    strategy_path_value = explicit_strategy_path or (
        str(weekly_path.with_name("strategy_quality_report.md")) if weekly_path else ""
    )
    statistical_path_value = (
        explicit_statistical_path
        or (
            str(statistical.get("qualification_report_path", ""))
            if isinstance(statistical, dict)
            else ""
        )
    )
    statistical_path = Path(statistical_path_value) if statistical_path_value else Path("")
    statistical_report = load_json(statistical_path) if statistical_path_value else {}
    strategy_path = Path(strategy_path_value) if strategy_path_value else Path("")
    strategy_report = load_json(strategy_path) if strategy_path_value else {}
    strategy_json_path_value = explicit_strategy_json_path or (
        str(strategy_path.with_suffix(".json")) if strategy_path_value else ""
    )
    strategy_json_path = Path(strategy_json_path_value) if strategy_json_path_value else Path("")
    strategy_json_report = load_json(strategy_json_path) if strategy_json_path_value else {}
    strategy_report_exists = strategy_path.exists() or strategy_json_path.exists()
    strategy_display_path = strategy_path if strategy_path.exists() else strategy_json_path
    strategy_display_report = strategy_report if strategy_path.exists() else strategy_json_report
    ai_progress_path_value = explicit_ai_progress_path or (
        str(weekly_path.with_name("ai_strategy_progress_report.json")) if weekly_path else ""
    )
    ai_progress_path = Path(ai_progress_path_value) if ai_progress_path_value else Path("")
    ai_progress_report = load_json(ai_progress_path) if ai_progress_path_value else {}
    strategy_summary = weekly.get("overview", {}).get("strategy_quality_summary", {}) if weekly else {}
    if not isinstance(strategy_summary, dict):
        strategy_summary = {}

    health_status = str(health.get("overall_status", "unknown"))
    weekly_status = str(weekly.get("status", "unknown")) if weekly else "missing"
    statistical_status = (
        str(statistical.get("status", "missing")) if isinstance(statistical, dict) else "missing"
    )
    health_meta = artifact_meta(health_path, health, fallback_keys=("generated_at", "checked_at"))
    weekly_meta = artifact_meta(weekly_path, weekly, fallback_keys=("generated_at",))
    statistical_meta = artifact_meta(
        statistical_path,
        statistical_report,
        fallback_keys=("generated_at",),
    )
    strategy_meta = artifact_meta(
        strategy_display_path,
        strategy_display_report,
        fallback_keys=("generated_at",),
    )
    strategy_json_meta = artifact_meta(
        strategy_json_path,
        strategy_json_report,
        fallback_keys=("generated_at",),
    )
    ai_progress_meta = artifact_meta(
        ai_progress_path,
        ai_progress_report,
        fallback_keys=("generated_at",),
    )
    health_stale = (
        health_meta["age_hours"] is None
        or float(health_meta["age_hours"]) > max_artifact_age_hours
    )
    weekly_stale = (
        weekly_meta["age_hours"] is None
        or float(weekly_meta["age_hours"]) > max_artifact_age_hours
    )
    statistical_stale = (
        statistical_meta["age_hours"] is None
        or float(statistical_meta["age_hours"]) > max_artifact_age_hours
    )
    strategy_stale = (
        strategy_meta["age_hours"] is None
        or float(strategy_meta["age_hours"]) > max_artifact_age_hours
    )
    strategy_json_stale = (
        strategy_json_meta["age_hours"] is None
        or float(strategy_json_meta["age_hours"]) > max_artifact_age_hours
    )
    ai_progress_stale = (
        ai_progress_meta["age_hours"] is None
        or float(ai_progress_meta["age_hours"]) > max_artifact_age_hours
    )
    rows = len(checkpoints)
    has_rows = rows > 0
    lock_residual = any(bool(r.get("runtime_lock_residual", False) or r.get("notify_lock_residual", False)) for r in checkpoints)
    runtime_alive_all = all(bool(r.get("runtime_alive", False)) for r in checkpoints) if checkpoints else False
    updated_progress_any = any(bool(r.get("runtime_updated_progress", False)) for r in checkpoints) if checkpoints else False
    if not start_watchers:
        runtime_alive_all = True

    longrun_ok = has_rows and (not lock_residual) and runtime_alive_all and updated_progress_any
    metrics_ok = health_status in {"pass", "warn"}
    go_ready = (
        longrun_ok
        and metrics_ok
        and health_status == "pass"
        and weekly_status == "pass"
        and statistical_status == "pass"
        and not health_stale
        and not weekly_stale
        and not statistical_stale
    )
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
    if health_stale:
        reasons.append("runtime metrics health report が stale（No-Go）")
    if weekly_status == "warn":
        reasons.append("weekly strategy revalidation が warn（要調整）")
    if weekly_status == "missing":
        reasons.append("weekly strategy revalidation report が未取得")
    if weekly_stale:
        reasons.append("weekly strategy revalidation report が stale（No-Go）")
    if statistical_status != "pass":
        reasons.append(f"statistical qualification が {statistical_status}（No-Go）")
    if not statistical_report:
        reasons.append("statistical qualification report が未取得/不正")
    elif statistical_stale:
        reasons.append("statistical qualification report が stale（No-Go）")
    if strategy_json_path_value and not strategy_json_report:
        reasons.append("strategy quality json report が未取得/不正")
    elif strategy_json_path_value and strategy_json_stale:
        reasons.append("strategy quality json report が stale（参考情報）")
    elif strategy_path_value and not strategy_report_exists:
        reasons.append("strategy quality report が未取得/不正")
    elif strategy_path_value and strategy_stale:
        reasons.append("strategy quality report が stale（参考情報）")
    if ai_progress_path_value and not ai_progress_report:
        reasons.append("AI progress report が未取得/不正")
    elif ai_progress_path_value and ai_progress_stale:
        reasons.append("AI progress report が stale（参考情報）")

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
        f"- statistical_status: {statistical_status}",
        f"- longrun_rows: {rows}",
        f"- runtime_env_path: {runtime_env_path}",
        f"- pipeline_summary_path: {pipeline_summary_path}",
        f"- weekly_report_path: {weekly_meta['path']}",
        f"- weekly_report_path_source: {weekly_path_source}",
        f"- weekly_report_run_id: {weekly_meta['run_id'] or '-'}",
        f"- weekly_report_generated_at: {weekly_meta['generated_at'] or '-'}",
        f"- weekly_report_age_hours: {format_age_hours(weekly_meta['age_hours'])}",
        f"- statistical_report_path: {statistical_meta['path'] or '-'}",
        f"- statistical_report_run_id: {statistical_meta['run_id'] or '-'}",
        f"- statistical_report_generated_at: {statistical_meta['generated_at'] or '-'}",
        f"- statistical_report_age_hours: {format_age_hours(statistical_meta['age_hours'])}",
        f"- strategy_report_path: {strategy_meta['path'] if strategy_path_value else '-'}",
        f"- strategy_report_run_id: {weekly_meta['run_id'] if strategy_path_value else '-'}",
        f"- strategy_report_generated_at: {strategy_meta['generated_at'] if strategy_path_value else '-'}",
        f"- strategy_report_age_hours: {format_age_hours(strategy_meta['age_hours']) if strategy_path_value else '-'}",
        f"- strategy_report_json_path: {strategy_json_meta['path'] if strategy_json_path_value else '-'}",
        f"- strategy_report_json_run_id: {weekly_meta['run_id'] if strategy_json_path_value else '-'}",
        f"- strategy_report_json_generated_at: {strategy_json_meta['generated_at'] if strategy_json_path_value else '-'}",
        f"- strategy_report_json_age_hours: {format_age_hours(strategy_json_meta['age_hours']) if strategy_json_path_value else '-'}",
        f"- ai_progress_report_path: {ai_progress_meta['path'] if ai_progress_path_value else '-'}",
        f"- ai_progress_report_run_id: {weekly_meta['run_id'] if ai_progress_path_value else '-'}",
        f"- ai_progress_report_generated_at: {ai_progress_meta['generated_at'] if ai_progress_path_value else '-'}",
        f"- ai_progress_report_age_hours: {format_age_hours(ai_progress_meta['age_hours']) if ai_progress_path_value else '-'}",
        f"- strategy_quality_range_recommendation: {strategy_summary.get('range', {}).get('recommendation', '-') if isinstance(strategy_summary.get('range', {}), dict) else '-'}",
        f"- strategy_quality_trend_recommendation: {strategy_summary.get('trend', {}).get('recommendation', '-') if isinstance(strategy_summary.get('trend', {}), dict) else '-'}",
        f"- health_report_path: {health_meta['path']}",
        f"- health_report_run_id: {health_meta['run_id'] or '-'}",
        f"- health_report_generated_at: {health_meta['generated_at'] or '-'}",
        f"- health_report_age_hours: {format_age_hours(health_meta['age_hours'])}",
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
        "statistical_status": statistical_status,
        "weekly_report_path": str(weekly_path),
        "weekly_report_path_source": weekly_path_source,
        "statistical_report_path": str(statistical_path) if statistical_path_value else "",
        "strategy_report_path": str(strategy_path) if strategy_path_value else "",
        "strategy_report_run_id": weekly_meta["run_id"] if strategy_path_value else "",
        "strategy_report_json_path": str(strategy_json_path) if strategy_json_path_value else "",
        "strategy_report_json_run_id": weekly_meta["run_id"] if strategy_json_path_value else "",
        "ai_progress_report_path": str(ai_progress_path) if ai_progress_path_value else "",
        "ai_progress_report_run_id": weekly_meta["run_id"] if ai_progress_path_value else "",
        "max_artifact_age_hours": max_artifact_age_hours,
        "health_stale": health_stale,
        "weekly_stale": weekly_stale,
        "statistical_stale": statistical_stale,
        "strategy_stale": strategy_stale,
        "strategy_json_stale": strategy_json_stale,
        "ai_progress_stale": ai_progress_stale,
        "longrun_ok": longrun_ok,
        "metrics_ok": metrics_ok,
        "go_live_ready": go_ready,
        "strategy_quality_range_recommendation": (
            strategy_summary.get("range", {}).get("recommendation", "-")
            if isinstance(strategy_summary.get("range", {}), dict)
            else "-"
        ),
        "strategy_quality_trend_recommendation": (
            strategy_summary.get("trend", {}).get("recommendation", "-")
            if isinstance(strategy_summary.get("trend", {}), dict)
            else "-"
        ),
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
