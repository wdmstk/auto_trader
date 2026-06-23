from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pytest

from auto_trader.orchestrator.dryrun import (
    DryRunStep,
    _finalize,
    _notify_test_step,
    _run_step,
    _to_obj_dict,
    cast_obj,
    run_dryrun_orchestration,
)


def test_run_step_captures_exception() -> None:
    def failing() -> dict[str, object]:
        raise ValueError("boom")

    started, ok, details, finished = _run_step("test_step", failing)
    assert ok is False
    assert details["error_reason"] == "boom"
    assert details["step"] == "test_step"


def test_run_step_success() -> None:
    def ok_step() -> dict[str, object]:
        return {"key": "value"}

    started, ok, details, finished = _run_step("ok_step", ok_step)
    assert ok is True
    assert details["key"] == "value"


def test_finalize_pass(tmp_path: Path) -> None:
    steps = [
        DryRunStep("a", True, {}, "t1", "t2"),
        DryRunStep("b", True, {}, "t3", "t4"),
    ]
    result = _finalize(steps, tmp_path)
    assert result["overall_status"] == "pass"
    report_path = Path(str(result["report_path"]))
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["overall_status"] == "pass"
    assert len(report["steps"]) == 2


def test_finalize_fail(tmp_path: Path) -> None:
    steps = [
        DryRunStep("a", True, {}, "t1", "t2"),
        DryRunStep("b", False, {"reason": "error"}, "t3", "t4"),
    ]
    result = _finalize(steps, tmp_path)
    assert result["overall_status"] == "fail"


def test_notify_test_step_all_succeed() -> None:
    class FakeNotifier:
        def send(self, alert: Any) -> Any:
            from auto_trader.notify.models import SendResult

            return SendResult(
                channel="test",
                alert_code=alert.alert_code,
                sent_at=alert.detected_at,
                success=True,
                response_code=200,
                error_reason="",
            )

    result = _notify_test_step([FakeNotifier(), FakeNotifier()])
    assert result["success"] is True
    assert result["count"] == 2


def test_notify_test_step_one_fails() -> None:
    class OkNotifier:
        def send(self, alert: Any) -> Any:
            from auto_trader.notify.models import SendResult

            return SendResult(
                channel="ok",
                alert_code=alert.alert_code,
                sent_at=alert.detected_at,
                success=True,
                response_code=200,
                error_reason="",
            )

    class FailNotifier:
        def send(self, alert: Any) -> Any:
            from auto_trader.notify.models import SendResult

            return SendResult(
                channel="fail",
                alert_code=alert.alert_code,
                sent_at=alert.detected_at,
                success=False,
                response_code=500,
                error_reason="error",
            )

    result = _notify_test_step([OkNotifier(), FailNotifier()])
    assert result["success"] is False
    assert result["count"] == 2


def test_notify_test_step_empty_notifiers() -> None:
    result = _notify_test_step([])
    assert result["success"] is False
    assert result["count"] == 0


def test_notify_test_step_skips_notifier_without_send() -> None:
    class NoSend:
        pass

    result = _notify_test_step([NoSend()])
    assert result["count"] == 0
    assert result["success"] is False


def test_cast_obj_primitives() -> None:
    assert cast_obj("hello") == "hello"
    assert cast_obj(42) == 42
    assert cast_obj(3.14) == 3.14
    assert cast_obj(True) is True
    assert cast_obj(None) is None


def test_cast_obj_list() -> None:
    result = cast_obj([1, "a", None])
    assert result == [1, "a", None]


def test_cast_obj_dict() -> None:
    result = cast_obj({"k": 1, "v": "x"})
    assert result == {"k": 1, "v": "x"}


def test_cast_obj_fallback_to_str() -> None:
    result = cast_obj(object())
    assert isinstance(result, str)


def test_to_obj_dict_from_dict() -> None:
    result = _to_obj_dict({"a": 1, "b": [2, 3]})
    assert result["a"] == 1
    assert result["b"] == [2, 3]


def test_to_obj_dict_from_non_dict() -> None:
    result = _to_obj_dict("string_value")
    assert result["value"] == "string_value"


def test_dryrun_with_notify_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from auto_trader.notify.models import SendResult

    class StubNotifier:
        channel_name = "stub"

        def send(self, alert: Any) -> SendResult:
            return SendResult(
                channel="stub",
                alert_code=alert.alert_code,
                sent_at=alert.detected_at,
                success=True,
                response_code=200,
                error_reason="",
            )

    monkeypatch.setattr(
        "auto_trader.orchestrator.dryrun.build_notifiers_from_env",
        lambda: [StubNotifier()],
    )

    ts = datetime(2026, 1, 1, tzinfo=UTC)
    signals = tmp_path / "signals.parquet"
    risk = tmp_path / "risk.parquet"
    runtime = tmp_path / "runtime.json"
    pd.DataFrame(
        [
            {
                "symbol": "BTCUSDT",
                "timestamp": ts,
                "entry_signal": True,
                "pass_filter": True,
                "regime": "RANGE",
            }
        ]
    ).to_parquet(signals, index=False)
    pd.DataFrame(
        [{"timestamp": ts, "risk_blocked": False, "current_dd_pct": 1.0}]
    ).to_parquet(risk, index=False)
    runtime.write_text(
        json.dumps({"trading_enabled": True, "emergency_stop": False}),
        encoding="utf-8",
    )

    out = run_dryrun_orchestration(
        signals_path=signals,
        risk_eval_path=risk,
        runtime_state_path=runtime,
        output_dir=tmp_path / "out",
    )
    assert out["overall_status"] == "pass"
    steps = cast(list[dict[str, Any]], out["steps"])
    notify_step = [s for s in steps if s["step"] == "notify_test"][0]
    assert notify_step["success"] is True
