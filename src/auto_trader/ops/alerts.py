from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd


@dataclass(frozen=True)
class AlertThresholds:
    runtime_stale_warn_sec: int = 30
    runtime_stale_critical_sec: int = 120
    risk_stale_warn_sec: int = 30
    risk_stale_critical_sec: int = 120
    reject_rate_warn: float = 0.2
    max_dd_pct: float = 15.0


@dataclass(frozen=True)
class AlertEvent:
    alert_code: str
    severity: str
    detected_at: str
    source: str
    summary: str
    action_required: str


def evaluate_alerts(
    *,
    runtime_state_path: str | Path,
    risk_eval_path: str | Path,
    order_events_path: str | Path | None = None,
    thresholds: AlertThresholds | None = None,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    cfg = thresholds or AlertThresholds()
    ref = now or datetime.now(UTC)
    alerts: list[AlertEvent] = []

    runtime = _read_json(Path(runtime_state_path))
    if runtime is None:
        alerts.append(
            _alert(
                code="RUNTIME_STATE_INVALID",
                severity="critical",
                source="runtime",
                summary="runtime control state is invalid or unreadable",
                action="validate runtime watcher output and state json",
                now=ref,
            )
        )
    else:
        runtime_updated_at = _parse_dt(runtime.get("updated_at"))
        if runtime_updated_at is None:
            alerts.append(
                _alert(
                    code="RUNTIME_STATE_INVALID",
                    severity="critical",
                    source="runtime",
                    summary="runtime updated_at is missing or invalid",
                    action="repair runtime state writer and reprocess events",
                    now=ref,
                )
            )
        else:
            runtime_stale_sec = (ref - runtime_updated_at).total_seconds()
            if runtime_stale_sec >= cfg.runtime_stale_critical_sec:
                alerts.append(
                    _alert(
                        code="RUNTIME_STALE",
                        severity="critical",
                        source="runtime",
                        summary=f"runtime state stale: {int(runtime_stale_sec)} sec",
                        action="trigger emergency stop and restart runtime watcher",
                        now=ref,
                    )
                )
            elif runtime_stale_sec >= cfg.runtime_stale_warn_sec:
                alerts.append(
                    _alert(
                        code="RUNTIME_STALE",
                        severity="warning",
                        source="runtime",
                        summary=f"runtime state stale: {int(runtime_stale_sec)} sec",
                        action="re-check in next cycle and inspect watcher health",
                        now=ref,
                    )
                )
        if bool(runtime.get("emergency_stop", False)):
            alerts.append(
                _alert(
                    code="EMERGENCY_ACTIVE",
                    severity="critical",
                    source="runtime",
                    summary="emergency_stop is active",
                    action="keep trading disabled until manual release decision",
                    now=ref,
                )
            )

    risk_df = _read_parquet(Path(risk_eval_path))
    if risk_df is None or risk_df.empty:
        alerts.append(
            _alert(
                code="RISK_DATA_INVALID",
                severity="critical",
                source="risk",
                summary="risk eval data is missing or unreadable",
                action="verify risk pipeline output and data freshness",
                now=ref,
            )
        )
    else:
        last = risk_df.iloc[-1]
        risk_ts = _parse_dt(last.get("timestamp"))
        if risk_ts is None:
            alerts.append(
                _alert(
                    code="RISK_DATA_INVALID",
                    severity="critical",
                    source="risk",
                    summary="risk timestamp is missing or invalid",
                    action="repair risk timestamp serialization",
                    now=ref,
                )
            )
        else:
            risk_stale_sec = (ref - risk_ts).total_seconds()
            if risk_stale_sec >= cfg.risk_stale_critical_sec:
                alerts.append(
                    _alert(
                        code="RISK_DATA_STALE",
                        severity="critical",
                        source="risk",
                        summary=f"risk data stale: {int(risk_stale_sec)} sec",
                        action="trigger emergency stop and recover risk pipeline",
                        now=ref,
                    )
                )
            elif risk_stale_sec >= cfg.risk_stale_warn_sec:
                alerts.append(
                    _alert(
                        code="RISK_DATA_STALE",
                        severity="warning",
                        source="risk",
                        summary=f"risk data stale: {int(risk_stale_sec)} sec",
                        action="re-check risk pipeline in next cycle",
                        now=ref,
                    )
                )
        dd = _to_float(last.get("current_dd_pct"))
        if dd > cfg.max_dd_pct:
            alerts.append(
                _alert(
                    code="RISK_DD_BREACH",
                    severity="critical",
                    source="risk",
                    summary=f"drawdown breach: {dd:.2f}% > {cfg.max_dd_pct:.2f}%",
                    action="stop new entries and require manual recovery approval",
                    now=ref,
                )
            )

    if order_events_path is not None:
        order_df = _read_parquet(Path(order_events_path))
        if order_df is not None and not order_df.empty:
            reject_rate = _reject_rate(order_df)
            if reject_rate >= cfg.reject_rate_warn:
                alerts.append(
                    _alert(
                        code="ORDER_REJECT_SPIKE",
                        severity="warning",
                        source="execution",
                        summary=f"reject rate spike: {reject_rate:.2f}",
                        action="inspect gateway reasons and exchange connectivity",
                        now=ref,
                    )
                )

    return [asdict(a) for a in alerts]


def _alert(
    *,
    code: str,
    severity: str,
    source: str,
    summary: str,
    action: str,
    now: datetime,
) -> AlertEvent:
    return AlertEvent(
        alert_code=code,
        severity=severity,
        detected_at=now.isoformat(),
        source=source,
        summary=summary,
        action_required=action,
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _read_parquet(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _parse_dt(v: object) -> datetime | None:
    try:
        ts = pd.Timestamp(cast(Any, v))
    except Exception:
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    out = ts.to_pydatetime()
    if not isinstance(out, datetime):
        return None
    return out


def _to_float(v: object) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _reject_rate(df: pd.DataFrame) -> float:
    if "status" not in df.columns:
        return 0.0
    total = len(df)
    if total == 0:
        return 0.0
    rejected = int((df["status"].astype(str) == "rejected").sum())
    return rejected / total
