from __future__ import annotations

from pathlib import Path

from auto_trader.analysis.candidates import (
    CandidateThresholds,
    recommend_symbol_candidates,
    write_candidate_report,
)


def test_recommend_symbol_candidates_classifies_rows(tmp_path: Path) -> None:
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
                "closed_trades_mean": 3.0,
            },
            {
                "symbol": "BTCUSDT",
                "timeframe": "30m",
                "strategy": "trend",
                "pf_mean": 0.95,
                "expectancy_bps_mean": 3.0,
                "period_pnl_mean": 1.0,
                "max_dd_mean": 0.05,
                "closed_trades_mean": 2.0,
            },
            {
                "symbol": "SOLUSDT",
                "timeframe": "1h",
                "strategy": "range",
                "pf_mean": 0.5,
                "expectancy_bps_mean": -1.0,
                "period_pnl_mean": -0.5,
                "max_dd_mean": 0.2,
                "closed_trades_mean": 2.0,
            },
        ]
    }

    out = recommend_symbol_candidates(summary, thresholds=CandidateThresholds())
    assert out["core_symbols"] == ["ETHUSDT"]
    assert out["probe_symbols"] == ["BTCUSDT"]
    assert out["watchlist_symbols"] == ["SOLUSDT"]
    assert out["timeframes"] == ["15m", "30m", "1h"]
    assert out["best_by_symbol_strategy"][0]["symbol"] == "ETHUSDT"

    json_path = tmp_path / "candidate_report.json"
    saved = write_candidate_report(summary, json_path=json_path)
    assert json_path.exists()
    assert saved["status"] == "pass"
