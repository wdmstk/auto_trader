from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from auto_trader.notify.channels import Notifier
from auto_trader.notify.models import SendResult, alert_from_row
from auto_trader.stateio import FileLock, atomic_write_json, read_json_with_recovery


@dataclass(frozen=True)
class NotifyPolicy:
    warning_to_slack: bool = False
    warning_to_email: bool = False
    warning_to_webhook: bool = True
    cooldown_sec: int = 300
    degraded_threshold: int = 3


class NotificationService:
    def __init__(
        self,
        *,
        notifiers: list[Notifier],
        policy: NotifyPolicy | None = None,
        state_path: str | Path = "data/ops/notify_state.json",
        lock_timeout_sec: float = 1.0,
    ) -> None:
        self.notifiers = notifiers
        self.policy = policy or NotifyPolicy()
        self.state_path = Path(state_path)
        self.lock_timeout_sec = lock_timeout_sec

    def _lock_path(self) -> Path:
        return self.state_path.with_suffix(f"{self.state_path.suffix}.lock")

    def dispatch(self, alert_rows: list[dict[str, str]]) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        state = self._read_state()
        now = datetime.now(UTC)
        for row in alert_rows:
            alert = alert_from_row(row)
            dedupe_key = f"{alert.alert_code}|{alert.summary}"
            if self._is_suppressed(state, dedupe_key, now):
                continue
            sent_any = False
            for notifier in self.notifiers:
                if not self._channel_enabled(alert.severity, notifier.channel_name):
                    continue
                result = notifier.send(alert)
                result = SendResult(
                    channel=result.channel,
                    alert_code=result.alert_code,
                    sent_at=now.isoformat(),
                    success=result.success,
                    response_code=result.response_code,
                    error_reason=result.error_reason,
                )
                out.append(asdict(result))
                fail_key = f"__fail__|{notifier.channel_name}"
                fail_count = int(state.get(fail_key, "0"))
                if result.success:
                    state[fail_key] = "0"
                else:
                    fail_count += 1
                    state[fail_key] = str(fail_count)
                    if fail_count >= self.policy.degraded_threshold:
                        out.append(
                            asdict(
                                SendResult(
                                    channel=notifier.channel_name,
                                    alert_code="NOTIFY_CHANNEL_DEGRADED",
                                    sent_at=now.isoformat(),
                                    success=False,
                                    response_code=result.response_code,
                                    error_reason=f"degraded_after_{fail_count}_failures",
                                )
                            )
                        )
                sent_any = True
            if sent_any:
                state[dedupe_key] = now.isoformat()
        self._write_state(state)
        return out

    def _channel_enabled(self, severity: str, channel: str) -> bool:
        if severity == "critical":
            return True
        if severity != "warning":
            return True
        if channel == "slack":
            return self.policy.warning_to_slack
        if channel == "email":
            return self.policy.warning_to_email
        if channel == "webhook":
            return self.policy.warning_to_webhook
        return True

    def _is_suppressed(self, state: dict[str, str], key: str, now: datetime) -> bool:
        prev = state.get(key)
        if prev is None:
            return False
        try:
            prev_dt = datetime.fromisoformat(prev)
        except (ValueError, TypeError):
            return False
        return (now - prev_dt).total_seconds() < self.policy.cooldown_sec

    def _read_state(self) -> dict[str, str]:
        with FileLock(self._lock_path(), timeout_sec=self.lock_timeout_sec):
            payload = read_json_with_recovery(self.state_path)
        if not isinstance(payload, dict):
            return {}
        out: dict[str, str] = {}
        for k, v in payload.items():
            out[str(k)] = str(v)
        return out

    def _write_state(self, state: dict[str, str]) -> None:
        payload: dict[str, object] = {k: v for k, v in state.items()}
        with FileLock(self._lock_path(), timeout_sec=self.lock_timeout_sec):
            atomic_write_json(self.state_path, payload)
