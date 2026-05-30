from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from auto_trader.ml.dataset import add_timeseries_split, build_dataset


def _mk_frames(n: int = 40) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for i in range(n):
        rows.append(
            {
                "symbol": "BTCUSDT",
                "timeframe": "1m",
                "timestamp": base + timedelta(minutes=i),
                "rsi": 40 + (i % 10),
                "atr": 1.0 + (i * 0.01),
                "bb_width": 0.05,
                "momentum_persistence": 0.7,
                "breakout_persistence": 0.7,
                "trend_efficiency": 0.2,
            }
        )
    f = pd.DataFrame(rows)
    r = f[["symbol", "timeframe", "timestamp"]].copy()
    r["regime"] = "TREND"
    r["is_trade_allowed"] = True
    s = f[["symbol", "timeframe", "timestamp"]].copy()
    s["entry_signal"] = True
    labels = f[["symbol", "timeframe", "timestamp"]].copy()
    labels["label"] = [1 if i % 2 == 0 else 0 for i in range(n)]
    return f, r, s, labels


def test_build_dataset_and_split() -> None:
    f, r, s, labels = _mk_frames()
    art = build_dataset(features_df=f, regime_df=r, signals_df=s, labels_df=labels)
    out = add_timeseries_split(art.dataset, train_ratio=0.6, valid_ratio=0.2)
    assert "split" in out.columns
    assert out["timestamp"].is_monotonic_increasing
    assert set(out["split"].unique()) == {"train", "valid", "test"}


def test_build_dataset_detects_duplicated_keys() -> None:
    f, r, s, labels = _mk_frames()
    f = pd.concat([f, f.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicated keys"):
        build_dataset(features_df=f, regime_df=r, signals_df=s, labels_df=labels)
