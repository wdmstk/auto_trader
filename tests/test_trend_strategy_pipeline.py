# mypy: disable-error-code=no-untyped-def

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.ml.model import load_model_artifacts, save_model_artifacts
from auto_trader.ml.pipeline import run_ml_pipeline
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


def test_trend_pipeline_applies_ml_artifact_filter(tmp_path: Path, monkeypatch) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    feats: list[dict[str, object]] = []
    regimes: list[dict[str, object]] = []
    pnls: list[dict[str, object]] = []
    labels: list[dict[str, object]] = []
    signals: list[dict[str, object]] = []
    for i in range(30):
        ts = base + timedelta(minutes=i)
        breakout = 0.9 if i % 2 == 0 else 0.1
        momentum = 0.9 if i % 2 == 0 else 0.1
        pullback = 0.8 if i % 2 == 0 else 0.2
        higher_high = 0.8 if i % 2 == 0 else 0.2
        feats.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "rsi": 50.0,
                "atr": 1.0,
                "bb_width": 0.05,
                "volume_ratio": 1.0,
                "ma_distance": 0.01,
                "trend_efficiency": 0.2,
                "wick_ratio": 0.7,
                "mean_reversion_distance": -0.2,
                "reversal_candle_flag": 1,
                "momentum_persistence": momentum,
                "breakout_persistence": breakout,
                "pullback_shallowness": pullback,
                "higher_high_persistence": higher_high,
                "feature_version": "v1",
                "generated_at": base,
                "is_warmup": False,
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
        labels.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "label": 1 if i % 2 == 0 else 0,
            }
        )
        signals.append(
            {
                "symbol": "ETHUSDT",
                "timeframe": "1m",
                "timestamp": ts,
                "entry_signal": True,
                "exit_signal": False,
                "regime": "TREND",
            }
        )

    fpath = tmp_path / "features.parquet"
    rpath = tmp_path / "regime.parquet"
    ppath = tmp_path / "pnl.parquet"
    lpath = tmp_path / "labels.parquet"
    spath = tmp_path / "signals.parquet"
    pd.DataFrame(feats).to_parquet(fpath, index=False)
    pd.DataFrame(regimes).to_parquet(rpath, index=False)
    pd.DataFrame(pnls).to_parquet(ppath, index=False)
    pd.DataFrame(labels).to_parquet(lpath, index=False)
    pd.DataFrame(signals).to_parquet(spath, index=False)

    _, _, trained = run_ml_pipeline(
        features_path=fpath,
        regime_path=rpath,
        signals_path=spath,
        labels_path=lpath,
        artifact_dir=tmp_path / "artifacts",
    )
    high_threshold = replace(trained, threshold=0.99)
    save_model_artifacts(high_threshold, tmp_path / "artifacts_high")
    loaded = load_model_artifacts(tmp_path / "artifacts_high")
    assert loaded.threshold == 0.99

    out, _ = build_and_save_trend_signals(
        features_path=fpath,
        regime_path=rpath,
        symbol="ETHUSDT",
        timeframe="1m",
        output_dir=tmp_path / "signals_out",
        pnl_path=ppath,
        ml_artifact_path=tmp_path / "artifacts_high",
    )
    assert "ml_score" in out.columns
    assert "ml_pass_filter" in out.columns
    assert "ml_model_version" in out.columns
    assert out["pass_filter"].equals(out["ml_pass_filter"])
    assert bool((~out["pass_filter"]).any()) is True

    monkeypatch.setenv("ML_ARTIFACT_PATH", str(tmp_path / "artifacts_high"))
    env_out, _ = build_and_save_trend_signals(
        features_path=fpath,
        regime_path=rpath,
        symbol="ETHUSDT",
        timeframe="1m",
        output_dir=tmp_path / "signals_env",
        pnl_path=ppath,
    )
    assert "ml_score" in env_out.columns
    assert "ml_score_source" in env_out.columns
    assert env_out["ml_score"].notna().any()
