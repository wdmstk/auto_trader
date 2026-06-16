from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pandas as pd

from auto_trader.strategy.session_gate import apply_session_gate, parse_session_hours


def test_parse_session_hours_wraps_midnight() -> None:
    hours = parse_session_hours("18-23,0-1")
    assert hours.hours == (0, 1, 18, 19, 20, 21, 22, 23)


def test_apply_session_gate_blocks_outside_hours() -> None:
    signals = pd.DataFrame(
        [
            {
                "symbol": "ETHUSDT",
                "timeframe": "15m",
                "timestamp": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
                "entry_signal": True,
                "add_signal": True,
                "pass_filter": True,
                "signal_reason_codes": ["TR_ENTRY_SCORE_OK"],
            },
            {
                "symbol": "ETHUSDT",
                "timeframe": "15m",
                "timestamp": datetime(2026, 1, 1, 3, 0, tzinfo=UTC),
                "entry_signal": True,
                "add_signal": True,
                "pass_filter": True,
                "signal_reason_codes": ["TR_ENTRY_SCORE_OK"],
            },
        ]
    )

    out = apply_session_gate(signals, allowed_hours="18-23,0-1")
    assert bool(out.loc[0, "session_allowed"]) is True
    assert bool(out.loc[0, "entry_signal"]) is True
    assert bool(out.loc[0, "pass_filter"]) is True
    assert bool(out.loc[1, "session_allowed"]) is False
    assert bool(out.loc[1, "entry_signal"]) is False
    assert bool(out.loc[1, "add_signal"]) is False
    assert bool(out.loc[1, "pass_filter"]) is False
    assert "SESSION_BLOCKED_OUT_OF_HOURS" in cast(list[str], out.loc[1, "signal_reason_codes"])
