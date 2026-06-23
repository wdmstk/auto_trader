"""Pure utility functions for the GUI module.

These helpers have no Streamlit dependency and perform no file I/O.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import pandas as pd


def safe_float(v: object, default: float = 0.0) -> float:
    if isinstance(v, bool):
        return float(int(v))
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return default
    return default


def safe_number(value: object) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return None


def latest_value(df: pd.DataFrame, col: str, default: str = "-") -> str:
    if df.empty or col not in df.columns:
        return default
    return str(df.iloc[-1][col])


def worker_state_key_parts(key: str) -> tuple[str, str, str]:
    parts = [part for part in str(key).split(":") if part]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1], ""
    if len(parts) == 1:
        return "", parts[0], ""
    return "", "", ""


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(cast(Any, value), utc=True, errors="coerce")
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    return cast(datetime, parsed.to_pydatetime())


def age_seconds(value: object, now: datetime | None = None) -> float | None:
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    ref = now or datetime.now(UTC)
    return max((ref - parsed).total_seconds(), 0.0)


def format_age(value: object, now: datetime | None = None) -> str:
    age = age_seconds(value, now=now)
    if age is None:
        return "unknown"
    if age < 60:
        return f"{age:.0f}s"
    if age < 3600:
        return f"{age / 60.0:.1f}m"
    return f"{age / 3600.0:.1f}h"


def freshness_level(
    value: object,
    *,
    now: datetime | None = None,
    warn_sec: int = 30,
    crit_sec: int = 120,
) -> str:
    age = age_seconds(value, now=now)
    if age is None:
        return "missing"
    if age >= crit_sec:
        return "critical"
    if age >= warn_sec:
        return "warning"
    return "ok"


def tail_text(text: str, limit: int = 20) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= limit:
        return "\n".join(lines)
    return "\n".join(lines[-limit:])


def csv_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(v).strip().upper() for v in values if str(v).strip()]


def downsample_for_chart(df: pd.DataFrame, max_points: int) -> pd.DataFrame:
    if max_points <= 0 or len(df) <= max_points:
        return df
    special_mask = pd.Series(False, index=df.index)
    for col in ("entry_signal", "exit_signal", "risk_blocked"):
        if col in df.columns:
            special_mask |= pd.to_numeric(df[col], errors="coerce").fillna(0).astype(bool)
    special = df[special_mask].copy()
    remaining = df[~special_mask].copy()
    budget = max_points - len(special)
    if budget <= 0:
        sampled = special.tail(max_points).copy()
    else:
        step = max(1, math.ceil(len(remaining) / budget)) if len(remaining) > budget else 1
        sampled = pd.concat([special, remaining.iloc[::step].copy()], axis=0)
    if sampled.index[-1] != df.index[-1]:
        sampled = pd.concat([sampled, df.tail(1)], axis=0)
    sampled = sampled[~sampled.index.duplicated(keep="last")].sort_index()
    return sampled


def worker_status_reason(row: Mapping[str, object]) -> str:
    status = str(row.get("status", ""))
    trade_status = str(row.get("trade_status", ""))
    if trade_status in {"entry", "exit", "add"}:
        return "\u767a\u6ce8\u6e08\u307f"
    mapping = {
        "already_processed": "\u540c\u4e00\u78ba\u5b9a\u8db3\u3092\u51e6\u7406\u6e08\u307f",
        "no_signal": "\u30b7\u30b0\u30ca\u30eb\u672a\u6210\u7acb",
        "missing_data": "\u30de\u30fc\u30b1\u30c3\u30c8\u30c7\u30fc\u30bf\u4e0d\u8db3",
        "not_enabled": "\u5bfe\u8c61\u5916\u30b7\u30f3\u30dc\u30eb",
        "disabled": "\u30b7\u30f3\u30dc\u30eb\u7121\u52b9",
        "risk_blocked": "\u30ea\u30b9\u30af\u5236\u9650\u3067\u505c\u6b62",
        "qty_zero": "\u30ed\u30c3\u30c8\u304c0",
        "no_action": "\u767a\u6ce8\u6761\u4ef6\u672a\u6210\u7acb",
    }
    return mapping.get(status, status or "unknown")


def signal_gate_summary(row: Mapping[str, object]) -> str:
    trade_status = str(row.get("trade_status", ""))
    if trade_status in {"entry", "exit", "add"}:
        return "\u767a\u6ce8\u6e08\u307f"
    parts: list[str] = []
    if "entry_signal" in row:
        parts.append("entry\u6210\u7acb" if bool(row.get("entry_signal", False)) else "entry\u672a\u6210\u7acb")
    if "exit_signal" in row and bool(row.get("exit_signal", False)):
        parts.append("exit\u6210\u7acb")
    if "add_signal" in row and bool(row.get("add_signal", False)):
        parts.append("add\u6210\u7acb")
    if "pass_filter" in row and not bool(row.get("pass_filter", False)):
        parts.append("filter\u672a\u901a\u904e")
    if "risk_blocked" in row and bool(row.get("risk_blocked", False)):
        parts.append("risk\u5236\u9650")
    reason_codes = str(row.get("reason_codes", "")).strip()
    if reason_codes:
        parts.append(reason_codes)
    if "gateway_status" in row and str(row.get("gateway_status", "")).strip():
        parts.append(str(row.get("gateway_status", "")))
    if not parts:
        return "signal snapshot unavailable"
    return "; ".join(parts)


def regime_mix_label(regime_snapshot: pd.DataFrame) -> str:
    if regime_snapshot.empty or "regime" not in regime_snapshot.columns:
        return "UNKNOWN"
    regimes = [str(value) for value in regime_snapshot["regime"].tolist() if str(value)]
    if not regimes:
        return "UNKNOWN"
    unique = sorted(set(regimes))
    if len(unique) == 1:
        return unique[0]
    if "SUSTAINED" in unique or "HIGH_VOL" in unique:
        return "HIGH_VOL MIX"
    if "SPIKE" in unique:
        return "SPIKE MIX"
    if "TREND" in unique and "RANGE" in unique:
        return "MIXED"
    return "MIXED"
