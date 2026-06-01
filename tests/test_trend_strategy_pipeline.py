from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.strategy.trend_pipeline import build_and_save_trend_signals


def test_build_and_save_trend_signals(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    feats: list[dict[str, object]] = []
    regimes: list[dict[str, object]] = []
    pnls: list[dict[str, object]] = []
    for i in range(16):
        ts = base + timedelta(minutes=i)
        feats.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "breakout_persistence": 0.8,
                "momentum_persistence": 0.8,
                "pullback_shallowness": 0.7,
                "higher_high_persistence": 0.7,
                "trend_efficiency": 0.2,
            }
        )
        regimes.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "regime": "TREND",
                "is_trade_allowed": True,
                "confidence": 0.8,
            }
        )
        pnls.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "unrealized_pnl_pct": 0.02 if i > 2 else -0.01,
            }
        )
    fpath = tmp_path / "features.parquet"
    rpath = tmp_path / "regime.parquet"
    ppath = tmp_path / "pnl.parquet"
    pd.DataFrame(feats).to_parquet(fpath, index=False)
    pd.DataFrame(regimes).to_parquet(rpath, index=False)
    pd.DataFrame(pnls).to_parquet(ppath, index=False)

    out, saved = build_and_save_trend_signals(
        features_path=fpath,
        regime_path=rpath,
        symbol="ETHUSDT",
        timeframe="1m",
        output_dir=tmp_path / "signals",
        pnl_path=ppath,
    )
    assert len(out) == 16
    assert Path(saved).exists()
    assert "add_signal" in out.columns
    assert "pass_filter" in out.columns
    assert "regime" in out.columns


def test_trend_pipeline_blocks_entries_when_drift_trade_block(tmp_path: Path) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    feats: list[dict[str, object]] = []
    regimes: list[dict[str, object]] = []
    pnls: list[dict[str, object]] = []
    for i in range(12):
        ts = base + timedelta(minutes=i)
        feats.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "breakout_persistence": 0.8,
                "momentum_persistence": 0.8,
                "pullback_shallowness": 0.7,
                "higher_high_persistence": 0.7,
                "trend_efficiency": 0.2,
            }
        )
        regimes.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "regime": "TREND",
                "is_trade_allowed": True,
                "confidence": 0.8,
            }
        )
        pnls.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "unrealized_pnl_pct": 0.02,
            }
        )
    fpath = tmp_path / "features.parquet"
    rpath = tmp_path / "regime.parquet"
    ppath = tmp_path / "pnl.parquet"
    dpath = tmp_path / "drift_report.json"
    pd.DataFrame(feats).to_parquet(fpath, index=False)
    pd.DataFrame(regimes).to_parquet(rpath, index=False)
    pd.DataFrame(pnls).to_parquet(ppath, index=False)
    dpath.write_text(json.dumps({"drift_trade_block": True}), encoding="utf-8")

    out, _ = build_and_save_trend_signals(
        features_path=fpath,
        regime_path=rpath,
        symbol="ETHUSDT",
        timeframe="1m",
        output_dir=tmp_path / "signals",
        pnl_path=ppath,
        drift_report_path=dpath,
    )
    assert bool(out["entry_signal"].any()) is False
