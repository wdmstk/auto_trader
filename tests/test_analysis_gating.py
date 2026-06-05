from __future__ import annotations

from pathlib import Path

from auto_trader.analysis.gating import (
    GatingThresholds,
    recommend_symbol_gating,
    write_gating_artifacts,
)


def test_recommend_symbol_gating_filters_by_metrics(tmp_path: Path) -> None:
    summary = {
        "rows": [
            {
                "symbol": "ETHUSDT",
                "timeframe": "15m",
                "strategy": "trend",
                "pf_mean": 2.2,
                "expectancy_bps_mean": 13.5,
                "period_pnl_mean": 4.5,
                "max_dd_mean": 0.02,
            },
            {
                "symbol": "XRPUSDT",
                "timeframe": "15m",
                "strategy": "range",
                "pf_mean": 1.3,
                "expectancy_bps_mean": 8.1,
                "period_pnl_mean": 1.2,
                "max_dd_mean": 0.01,
            },
            {
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "strategy": "trend",
                "pf_mean": 0.8,
                "expectancy_bps_mean": -1.0,
                "period_pnl_mean": -2.0,
                "max_dd_mean": 0.1,
            },
        ]
    }

    out = recommend_symbol_gating(summary, timeframe="15m", thresholds=GatingThresholds())
    assert out["trend_enabled_symbols"] == ["ETHUSDT"]
    assert out["range_enabled_symbols"] == ["XRPUSDT"]

    json_path = tmp_path / "gating.json"
    env_path = tmp_path / "gating.env"
    saved = write_gating_artifacts(summary, json_path=json_path, env_path=env_path, timeframe="15m")
    assert json_path.exists()
    assert env_path.exists()
    assert saved["status"] == "pass"
    env_text = env_path.read_text(encoding="utf-8")
    assert "TREND_ENABLED_SYMBOLS=ETHUSDT" in env_text
    assert "RANGE_ENABLED_SYMBOLS=XRPUSDT" in env_text
