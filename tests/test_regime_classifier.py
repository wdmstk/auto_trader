from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from auto_trader.regime.classifier import ALLOWED_REASON_CODES, RegimeConfig, classify_regime


def _feature_sample(rows: int = 80) -> pd.DataFrame:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    data: list[dict[str, object]] = []
    for i in range(rows):
        data.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": base + timedelta(minutes=i),
                "atr": 1.0 if i < 60 else 10.0,
                "bb_width": 0.05 if i < 50 else 0.2,
                "mean_reversion_distance": 0.5 if i < 50 else 0.1,
                "momentum_persistence": 0.2 if i < 50 else 0.9,
                "breakout_persistence": 0.2 if i < 50 else 0.9,
                "trend_efficiency": 0.1 if i < 50 else 0.5,
                "is_warmup": i < 10,
            }
        )
    return pd.DataFrame(data)


def test_classify_regime_output_contract() -> None:
    out = classify_regime(_feature_sample())
    required = {
        "symbol",
        "timeframe",
        "timestamp",
        "regime",
        "confidence",
        "volatility_state",
        "reason_codes",
        "is_trade_allowed",
    }
    assert required.issubset(out.columns)
    assert out["regime"].isin(["RANGE", "TREND", "HIGH_VOL"]).all()


def test_high_vol_disables_trading() -> None:
    out = classify_regime(_feature_sample(), RegimeConfig(high_vol_cooldown_bars=2))
    high_vol_rows = out[out["regime"] == "HIGH_VOL"]
    assert not high_vol_rows.empty
    assert (~high_vol_rows["is_trade_allowed"]).all()


def test_reason_codes_are_whitelisted() -> None:
    out = classify_regime(_feature_sample())
    for codes in out["reason_codes"]:
        for code in codes:
            assert code in ALLOWED_REASON_CODES
