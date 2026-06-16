from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from auto_trader.gui.overlay import build_overlay_frame, build_regime_segments


def test_build_overlay_frame_contains_expected_columns() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    ohlcv = pd.DataFrame(
        [
            {
                "timestamp": base + timedelta(minutes=i),
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.0 + i,
            }
            for i in range(3)
        ]
    )
    signals = pd.DataFrame(
        [
            {"timestamp": base, "entry_signal": True, "exit_signal": False, "ml_score": 0.8},
            {
                "timestamp": base + timedelta(minutes=1),
                "entry_signal": False,
                "exit_signal": True,
                "ml_score": 0.2,
            },
        ]
    )
    regime = pd.DataFrame(
        [
            {"timestamp": base, "regime": "RANGE"},
            {"timestamp": base + timedelta(minutes=1), "regime": "HIGH_VOL"},
        ]
    )
    risk = pd.DataFrame(
        [
            {"timestamp": base, "risk_blocked": False},
            {"timestamp": base + timedelta(minutes=1), "risk_blocked": True},
        ]
    )

    out = build_overlay_frame(ohlcv_df=ohlcv, signal_df=signals, regime_df=regime, risk_df=risk)
    assert len(out) == 3
    expected = {
        "timestamp",
        "close",
        "entry_marker",
        "exit_marker",
        "risk_block_marker",
        "ml_score",
        "regime",
        "regime_band",
    }
    assert expected.issubset(set(out.columns))
    assert out.iloc[0]["entry_marker"] == out.iloc[0]["close"]
    assert out.iloc[1]["exit_marker"] == out.iloc[1]["close"]
    assert out.iloc[1]["risk_block_marker"] == out.iloc[1]["close"]
    assert float(out.iloc[1]["regime_band"]) == 4.0


def test_build_regime_segments_groups_consecutive_runs() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    frame = pd.DataFrame(
        [
            {"timestamp": base, "regime": "RANGE"},
            {"timestamp": base + timedelta(minutes=1), "regime": "RANGE"},
            {"timestamp": base + timedelta(minutes=2), "regime": "TREND"},
            {"timestamp": base + timedelta(minutes=3), "regime": "TREND"},
            {"timestamp": base + timedelta(minutes=4), "regime": "HIGH_VOL"},
        ]
    )

    segments = build_regime_segments(frame)

    assert len(segments) == 3
    assert list(segments["regime"]) == ["RANGE", "TREND", "HIGH_VOL"]
    assert segments.iloc[0]["start"] == pd.Timestamp(base)
    assert segments.iloc[0]["end"] == pd.Timestamp(base + timedelta(minutes=2))


def test_build_overlay_frame_uses_position_size_ratio_as_ml_score_proxy() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    ohlcv = pd.DataFrame(
        [
            {
                "timestamp": base + timedelta(minutes=i),
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.0 + i,
            }
            for i in range(3)
        ]
    )
    signals = pd.DataFrame(
        [
            {
                "timestamp": base,
                "entry_signal": True,
                "exit_signal": False,
                "position_size_ratio": 0.1,
            }
        ]
    )

    out = build_overlay_frame(
        ohlcv_df=ohlcv,
        signal_df=signals,
        regime_df=pd.DataFrame(),
        risk_df=pd.DataFrame(),
    )

    assert float(out.iloc[0]["ml_score"]) == 0.1
    assert str(out.iloc[0]["ml_score_source"]) == "position_size_ratio"
