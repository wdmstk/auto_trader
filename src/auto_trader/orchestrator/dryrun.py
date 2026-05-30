from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from auto_trader.e2e.smoke import run_e2e_smoke
from auto_trader.notify.config import build_notifiers_from_env
from auto_trader.notify.models import AlertMessage
from auto_trader.ops.pipeline import run_alert_pipeline


@dataclass(frozen=True)
class DryRunStep:
    step: str
    success: bool
    details: dict[str, object]
    started_at: str
    finished_at: str


def run_dryrun_orchestration(
    *,
    signals_path: str | Path,
    risk_eval_path: str | Path,
    runtime_state_path: str | Path,
    output_dir: str | Path = "data/orchestrator",
) -> dict[str, object]:
    steps: list[DryRunStep] = []
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    s1, ok1, d1, done1 = _run_step(
        "e2e_smoke",
        lambda: run_e2e_smoke(
            signals_path=signals_path,
            risk_eval_path=risk_eval_path,
            runtime_state_path=runtime_state_path,
            output_dir=out_dir / "e2e",
        ),
    )
    e2e_ok = ok1 and str(d1.get("overall_status", "fail")) == "pass"
    steps.append(DryRunStep("e2e_smoke", e2e_ok, d1, s1, done1))
    if not e2e_ok:
        return _finalize(steps, out_dir)

    s2, ok2, d2, done2 = _run_step(
        "ops_alert",
        lambda: _ops_step(
            risk_eval_path=risk_eval_path,
            runtime_state_path=runtime_state_path,
            out_dir=out_dir,
        ),
    )
    steps.append(DryRunStep("ops_alert", ok2, d2, s2, done2))
    if not ok2:
        return _finalize(steps, out_dir)

    notifiers = build_notifiers_from_env()
    if not notifiers:
        now = datetime.now(UTC).isoformat()
        steps.append(
            DryRunStep(
                "notify_test",
                True,
                {"skipped": True, "reason": "notifier_not_configured"},
                now,
                now,
            )
        )
        return _finalize(steps, out_dir)

    s3, ok3, d3, done3 = _run_step("notify_test", lambda: _notify_test_step(notifiers))
    steps.append(DryRunStep("notify_test", ok3, d3, s3, done3))
    return _finalize(steps, out_dir)


def _ops_step(
    *,
    risk_eval_path: str | Path,
    runtime_state_path: str | Path,
    out_dir: Path,
) -> dict[str, object]:
    out, parquet_path, jsonl_path = run_alert_pipeline(
        runtime_state_path=runtime_state_path,
        risk_eval_path=risk_eval_path,
        output_dir=out_dir / "ops",
    )
    return {
        "count": len(out),
        "parquet_path": str(parquet_path),
        "jsonl_path": str(jsonl_path),
    }


def _notify_test_step(notifiers: Sequence[object]) -> dict[str, object]:
    alert = AlertMessage(
        alert_code="DRYRUN_NOTIFY_TEST",
        severity="critical",
        detected_at=datetime.now(UTC).isoformat(),
        source="orchestrator",
        summary="dry-run notify test",
        action_required="verify delivery",
    )
    results: list[dict[str, object]] = []
    for notifier in notifiers:
        send = getattr(notifier, "send", None)
        if send is None:
            continue
        r = send(alert)
        results.append(
            {
                "channel": getattr(r, "channel", ""),
                "success": bool(getattr(r, "success", False)),
                "response_code": int(getattr(r, "response_code", 0)),
                "error_reason": str(getattr(r, "error_reason", "")),
            }
        )
    ok = all(bool(row["success"]) for row in results) if results else False
    return {"count": len(results), "success": ok, "results": results}


def _run_step(
    step: str,
    fn: Callable[[], dict[str, object]],
) -> tuple[str, bool, dict[str, object], str]:
    started = datetime.now(UTC).isoformat()
    try:
        out = fn()
        finished = datetime.now(UTC).isoformat()
        return started, True, _to_obj_dict(out), finished
    except Exception as exc:
        finished = datetime.now(UTC).isoformat()
        return started, False, {"error_reason": str(exc), "step": step}, finished


def _finalize(steps: list[DryRunStep], out_dir: Path) -> dict[str, object]:
    overall = "pass" if all(s.success for s in steps) else "fail"
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "overall_status": overall,
        "steps": [asdict(s) for s in steps],
    }
    path = out_dir / "dryrun_report.json"
    path.write_text(json.dumps(report, ensure_ascii=True), encoding="utf-8")
    return {"overall_status": overall, "report_path": str(path), "steps": report["steps"]}


def _to_obj_dict(v: object) -> dict[str, object]:
    if isinstance(v, dict):
        return {str(k): cast_obj(val) for k, val in v.items()}
    return {"value": cast_obj(v)}


def cast_obj(v: object) -> object:
    if isinstance(v, str | int | float | bool) or v is None:
        return v
    if isinstance(v, list):
        return [cast_obj(x) for x in v]
    if isinstance(v, dict):
        return {str(k): cast_obj(val) for k, val in v.items()}
    return str(v)
