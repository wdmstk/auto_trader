from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

import pandas as pd

JST = ZoneInfo("Asia/Tokyo")
SESSION_BLOCK_REASON = "SESSION_BLOCKED_OUT_OF_HOURS"


@dataclass(frozen=True)
class SessionHours:
    hours: tuple[int, ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.hours)


def parse_session_hours(spec: str | None) -> SessionHours:
    if spec is None:
        return SessionHours()
    text = str(spec).strip()
    if not text:
        return SessionHours()

    hours: set[int] = set()
    for chunk in text.split(","):
        token = chunk.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start = _parse_hour(start_text)
            end = _parse_hour(end_text)
            if start <= end:
                hours.update(range(start, end + 1))
            else:
                hours.update(range(start, 24))
                hours.update(range(0, end + 1))
            continue
        hours.add(_parse_hour(token))

    return SessionHours(hours=tuple(sorted(hours)))


def apply_session_gate(
    signals_df: pd.DataFrame,
    *,
    allowed_hours: str | SessionHours | None,
) -> pd.DataFrame:
    session_hours = (
        parse_session_hours(allowed_hours)
        if not isinstance(allowed_hours, SessionHours)
        else allowed_hours
    )
    if not session_hours.enabled:
        out = signals_df.copy()
        out["session_allowed"] = True
        return out

    if "timestamp" not in signals_df.columns:
        raise ValueError("signals_df must contain timestamp for session gating")

    out = signals_df.copy()
    timestamp = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    if timestamp.isna().any():
        raise ValueError("signals_df contains invalid timestamp values")

    hours = timestamp.dt.tz_convert(JST).dt.hour
    session_allowed = hours.isin(session_hours.hours)
    out["session_allowed"] = session_allowed

    blocked_mask = ~session_allowed
    if blocked_mask.any():
        for column in ["entry_signal", "add_signal", "pass_filter"]:
            if column in out.columns:
                out.loc[blocked_mask, column] = False
                out[column] = out[column].fillna(False).astype(bool)
        if "signal_reason_codes" in out.columns:
            out["signal_reason_codes"] = [
                _append_reason_codes(value, SESSION_BLOCK_REASON, blocked)
                for value, blocked in zip(
                    out["signal_reason_codes"].tolist(),
                    blocked_mask.tolist(),
                    strict=False,
                )
            ]
    return out


def _parse_hour(text: str) -> int:
    hour = int(text.strip())
    if hour < 0 or hour > 23:
        raise ValueError(f"invalid session hour: {text!r}")
    return hour


def _append_reason_codes(value: object, reason: str, blocked: bool) -> list[str]:
    if not blocked:
        if isinstance(value, list):
            return list(value)
        return []
    if isinstance(value, list):
        codes = list(value)
    elif value is None or (isinstance(value, float) and pd.isna(value)):
        codes = []
    else:
        codes = [str(value)]
    if reason not in codes:
        codes.append(reason)
    return sorted(set(codes))
