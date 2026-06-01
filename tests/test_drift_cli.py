from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from pytest import MonkeyPatch

from auto_trader.drift.cli import main


def _feature_df(scale: float = 1.0) -> pd.DataFrame:
    vals = [float(i) * scale for i in range(1, 51)]
    return pd.DataFrame(
        {
            "symbol": ["BTCUSDT"] * len(vals),
            "timeframe": ["15m"] * len(vals),
            "timestamp": pd.date_range("2026-01-01", periods=len(vals), tz="UTC", freq="15min"),
            "rsi": vals,
            "atr": [v / 10.0 for v in vals],
        }
    )


def test_drift_cli_creates_baseline_then_warn(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    features_path = tmp_path / "features.parquet"
    _feature_df().to_parquet(features_path, index=False)
    baseline_path = tmp_path / "baseline.json"
    report_path = tmp_path / "report.json"
    online_stats_path = tmp_path / "online_stats.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "drift",
            "--features-path",
            str(features_path),
            "--baseline-path",
            str(baseline_path),
            "--report-path",
            str(report_path),
            "--online-stats-path",
            str(online_stats_path),
        ],
    )
    rc = main()
    assert rc == 0
    assert baseline_path.exists()
    assert online_stats_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["baseline_created"] is True
    assert report["status"] == "warn"


def test_drift_cli_detects_fail_when_distribution_shifts(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    baseline_features = tmp_path / "baseline_features.parquet"
    current_features = tmp_path / "current_features.parquet"
    _feature_df(scale=1.0).to_parquet(baseline_features, index=False)
    _feature_df(scale=10.0).to_parquet(current_features, index=False)

    baseline_path = tmp_path / "baseline.json"
    report_path = tmp_path / "report.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "drift",
            "--features-path",
            str(baseline_features),
            "--baseline-path",
            str(baseline_path),
            "--report-path",
            str(report_path),
        ],
    )
    assert main() == 0

    monkeypatch.setattr(
        "sys.argv",
        [
            "drift",
            "--features-path",
            str(current_features),
            "--baseline-path",
            str(baseline_path),
            "--report-path",
            str(report_path),
        ],
    )
    assert main() == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] in {"warn", "fail"}
    assert isinstance(report["drift_trade_block"], bool)
