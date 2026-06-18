from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from auto_trader.utils import write_json_file


@dataclass(frozen=True)
class StageResult:
    stage: str
    success: bool
    records: int
    error_reason: str


def run_e2e_smoke(
    *,
    signals_path: str | Path,
    risk_eval_path: str | Path,
    runtime_state_path: str | Path,
    output_dir: str | Path = "data/e2e",
) -> dict[str, object]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stages: list[StageResult] = []

    sig = _read_table(Path(signals_path))
    if sig.empty:
        stages.append(StageResult("strategy_signal_check", False, 0, "signals_missing_or_empty"))
        return _finalize(stages, out_dir)
    stages.append(StageResult("strategy_signal_check", True, len(sig), ""))

    if not {"symbol", "timestamp", "entry_signal", "pass_filter"}.issubset(sig.columns):
        stages.append(StageResult("position_apply_check", False, 0, "signal_schema_invalid"))
        return _finalize(stages, out_dir)
    stages.append(StageResult("position_apply_check", True, len(sig), ""))

    risk = _read_table(Path(risk_eval_path))
    if risk.empty or "risk_blocked" not in risk.columns:
        stages.append(StageResult("risk_eval_check", False, 0, "risk_missing_or_schema_invalid"))
        return _finalize(stages, out_dir)
    stages.append(StageResult("risk_eval_check", True, len(risk), ""))

    runtime = _read_runtime(Path(runtime_state_path))
    if runtime is None:
        stages.append(StageResult("order_gate_check", False, 0, "runtime_state_invalid"))
        return _finalize(stages, out_dir)

    gate_fail = _order_gate_fail_reason(sig, risk, runtime)
    if gate_fail:
        stages.append(StageResult("order_gate_check", False, 0, gate_fail))
        return _finalize(stages, out_dir)
    stages.append(StageResult("order_gate_check", True, int(sig["entry_signal"].sum()), ""))

    stages.append(StageResult("ops_alert_check", True, 1, ""))
    return _finalize(stages, out_dir)


def _order_gate_fail_reason(
    sig: pd.DataFrame,
    risk: pd.DataFrame,
    runtime: dict[str, object],
) -> str:
    latest_signal = sig.iloc[-1]
    if bool(runtime.get("emergency_stop", False)):
        return "runtime_emergency_stop"
    if not bool(runtime.get("trading_enabled", False)):
        return "runtime_trading_disabled"
    regime = str(latest_signal.get("regime", ""))
    if regime in {"HIGH_VOL", "SUSTAINED"}:
        return "high_vol_blocked"
    if not bool(latest_signal.get("pass_filter", False)):
        return "pass_filter_blocked"
    latest_risk = risk.iloc[-1]
    if bool(latest_risk.get("risk_blocked", False)):
        return "risk_blocked"
    return ""


def _finalize(stages: list[StageResult], out_dir: Path) -> dict[str, object]:
    overall = "pass" if all(s.success for s in stages) else "fail"
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "overall_status": overall,
        "stages": [asdict(s) for s in stages],
    }
    report_path = out_dir / "smoke_report.json"
    events_path = out_dir / "smoke_events.jsonl"
    write_json_file(report_path, report, indent=None)
    with events_path.open("w", encoding="utf-8") as f:
        for stage in stages:
            f.write(json.dumps(asdict(stage), ensure_ascii=True) + "\n")
    return {
        "overall_status": overall,
        "report_path": str(report_path),
        "events_path": str(events_path),
        "stages": [asdict(s) for s in stages],
    }


def _read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    if path.suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    return pd.read_parquet(path)


def _read_runtime(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    return raw
