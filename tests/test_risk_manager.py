from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pandas as pd
import pytest

from auto_trader.risk.manager import (
    RiskConfig,
    RiskManager,
    build_concentration_score,
    evaluate_portfolio_risk,
)

pytestmark = pytest.mark.smoke


def test_dd_limit_blocks() -> None:
    rm = RiskManager(RiskConfig(max_dd_pct=10.0))
    out = rm.evaluate(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        symbol="BTCUSDT",
        current_equity=8500.0,
        equity_peak=10000.0,
        symbol_exposure_pct=5.0,
        portfolio_exposure_pct=10.0,
        concentration_score=0.2,
    )
    assert bool(out["risk_blocked"]) is True
    dd_codes = cast(list[str], out["block_reason_codes"])
    assert "RISK_DD_LIMIT" in dd_codes


def test_exposure_limit_blocks() -> None:
    rm = RiskManager(
        RiskConfig(max_symbol_exposure_pct=10.0, max_portfolio_exposure_pct=15.0),
    )
    out = rm.evaluate(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        symbol="ETHUSDT",
        current_equity=10000.0,
        equity_peak=10000.0,
        symbol_exposure_pct=20.0,
        portfolio_exposure_pct=30.0,
        concentration_score=0.3,
    )
    assert bool(out["risk_blocked"]) is True
    exp_codes = cast(list[str], out["block_reason_codes"])
    assert "RISK_SYMBOL_EXPOSURE" in exp_codes
    assert "RISK_PORTFOLIO_EXPOSURE" in exp_codes


def test_emergency_state_blocks() -> None:
    rm = RiskManager()
    rm.emergency_stop()
    out = rm.evaluate(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        symbol="SOLUSDT",
        current_equity=10000.0,
        equity_peak=10000.0,
        symbol_exposure_pct=1.0,
        portfolio_exposure_pct=2.0,
        concentration_score=0.1,
    )
    assert bool(out["risk_blocked"]) is True
    em_codes = cast(list[str], out["block_reason_codes"])
    assert "RISK_EMERGENCY_STOP" in em_codes


def test_concentration_score() -> None:
    score = build_concentration_score({"BTCUSDT_exposure_pct": 40.0, "ETHUSDT_exposure_pct": 10.0})
    assert abs(score - 0.8) < 1e-9


def test_evaluate_portfolio_risk_frame() -> None:
    df = pd.DataFrame(
        [
            {
                "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
                "symbol": "BTCUSDT",
                "current_equity": 10000.0,
                "equity_peak": 10000.0,
                "symbol_exposure_pct": 5.0,
                "portfolio_exposure_pct": 8.0,
                "concentration_score": 0.2,
            },
            {
                "timestamp": datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
                "symbol": "BTCUSDT",
                "current_equity": 8000.0,
                "equity_peak": 10000.0,
                "symbol_exposure_pct": 5.0,
                "portfolio_exposure_pct": 8.0,
                "concentration_score": 0.2,
            },
        ]
    )
    out = evaluate_portfolio_risk(manager=RiskManager(RiskConfig(max_dd_pct=15.0)), risk_inputs=df)
    assert len(out) == 2
    assert out.loc[1, "risk_blocked"] is True or bool(out.loc[1, "risk_blocked"]) is True


def test_correlated_exposure_blocks() -> None:
    rm = RiskManager(RiskConfig(max_correlated_exposure_pct=30.0))
    out = rm.evaluate(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        symbol="BTCUSDT",
        current_equity=10000.0,
        equity_peak=10000.0,
        symbol_exposure_pct=5.0,
        portfolio_exposure_pct=20.0,
        concentration_score=0.2,
        correlated_exposure_pct=55.0,
    )
    assert bool(out["risk_blocked"]) is True
    codes = cast(list[str], out["block_reason_codes"])
    assert "RISK_CORRELATED_EXPOSURE" in codes
