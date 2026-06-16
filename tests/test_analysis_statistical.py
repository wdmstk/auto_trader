from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from auto_trader.analysis.statistical import (
    StatisticalThresholds,
    build_statistical_qualification,
)


def _write_route_artifacts(
    root: Path,
    *,
    strategy: str = "trend",
    oos_trades: int = 30,
    oos_days: int = 40,
) -> dict[str, object]:
    stamp = f"ETHUSDT_15m_{strategy}"
    base = datetime(2026, 1, 1, tzinfo=UTC)
    portfolio_rows = []
    for fold, offset, days in [(0, 0, 120), (1, 120, oos_days + 1)]:
        for day in range(days):
            portfolio_rows.append(
                {
                    "timestamp": base + timedelta(days=offset + day),
                    "fold": fold,
                    "drawdown": 0.01,
                }
            )
    closed_rows = []
    for idx in range(oos_trades):
        closed_rows.append(
            {
                "entry_ts": base + timedelta(days=121 + idx % max(oos_days, 1)),
                "exit_ts": base + timedelta(days=121 + idx % max(oos_days, 1), hours=1),
                "pnl": 10.0,
                "entry_notional": 1000.0,
                "return_bps": 100.0,
                "fold": 1,
            }
        )
    pd.DataFrame(portfolio_rows).to_parquet(root / f"walkforward_{stamp}_portfolio.parquet")
    pd.DataFrame(closed_rows).to_parquet(root / f"walkforward_{stamp}_closed_trades.parquet")
    (root / f"walkforward_{stamp}_meta.json").write_text("{}", encoding="utf-8")
    return {
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "strategy": strategy,
        "pf_mean": 2.0,
        "expectancy_bps_mean": 10.0,
        "period_pnl_mean": 10.0,
        "max_dd_mean": 0.01,
    }


def _thresholds(**overrides: object) -> StatisticalThresholds:
    values: dict[str, object] = {
        "bootstrap_samples": 200,
        "block_size": 3,
        "seed": 7,
    }
    values.update(overrides)
    return StatisticalThresholds(**values)  # type: ignore[arg-type]


def test_route_with_29_trades_fails_and_result_is_reproducible(tmp_path: Path) -> None:
    row = _write_route_artifacts(tmp_path, oos_trades=29)
    manifest = tmp_path / "frozen.json"
    first = build_statistical_qualification(
        {"rows": [row]},
        analysis_dir=tmp_path,
        manifest_path=manifest,
        execution_delay_bars=1,
        thresholds=_thresholds(min_strategy_trades=29),
        run_id="run-123",
        generated_at="2026-06-13T00:00:00+00:00",
    )
    second = build_statistical_qualification(
        {"rows": [row]},
        analysis_dir=tmp_path,
        manifest_path=manifest,
        execution_delay_bars=1,
        thresholds=_thresholds(min_strategy_trades=29),
        run_id="run-123",
        generated_at="2026-06-13T00:00:00+00:00",
    )

    assert first == second
    assert first["run_id"] == "run-123"
    assert first["generated_at"] == "2026-06-13T00:00:00+00:00"
    assert first["routes"][0]["status"] == "fail"
    assert "min_route_trades" in first["routes"][0]["reasons"]


def test_strategy_with_99_trades_fails(tmp_path: Path) -> None:
    row = _write_route_artifacts(tmp_path, oos_trades=99)
    report = build_statistical_qualification(
        {"rows": [row]},
        analysis_dir=tmp_path,
        manifest_path=tmp_path / "frozen.json",
        execution_delay_bars=1,
        thresholds=_thresholds(min_route_trades=30),
    )
    assert report["routes"][0]["status"] == "pass"
    assert report["strategies"][0]["status"] == "fail"
    assert "min_strategy_trades" in report["strategies"][0]["reasons"]


def test_short_oos_and_leakage_audit_fail(tmp_path: Path) -> None:
    row = _write_route_artifacts(tmp_path, oos_trades=100, oos_days=20)
    report = build_statistical_qualification(
        {"rows": [row]},
        analysis_dir=tmp_path,
        manifest_path=tmp_path / "frozen.json",
        execution_delay_bars=0,
        ml_label_horizon_bars=5,
        purge_bars=2,
        thresholds=_thresholds(),
    )
    assert "min_oos_days" in report["routes"][0]["reasons"]
    assert report["leakage_audit"]["status"] == "fail"
    assert "execution_delay_bars_lt_1" in report["leakage_audit"]["reasons"]
    assert "purge_bars_lt_ml_label_horizon" in report["leakage_audit"]["reasons"]


def test_frozen_manifest_detects_artifact_change(tmp_path: Path) -> None:
    row = _write_route_artifacts(tmp_path, oos_trades=100)
    manifest = tmp_path / "frozen.json"
    build_statistical_qualification(
        {"rows": [row]},
        analysis_dir=tmp_path,
        manifest_path=manifest,
        execution_delay_bars=1,
        thresholds=_thresholds(),
    )
    path = tmp_path / "walkforward_ETHUSDT_15m_trend_meta.json"
    path.write_text('{"changed": true}', encoding="utf-8")
    report = build_statistical_qualification(
        {"rows": [row]},
        analysis_dir=tmp_path,
        manifest_path=manifest,
        execution_delay_bars=1,
        thresholds=_thresholds(),
    )
    assert report["manifest_status"] == "fail"
    assert "frozen_manifest_mismatch" in report["leakage_audit"]["reasons"]


def test_confidence_interval_and_monte_carlo_can_block_route(tmp_path: Path) -> None:
    row = _write_route_artifacts(tmp_path, oos_trades=100)
    closed_path = tmp_path / "walkforward_ETHUSDT_15m_trend_closed_trades.parquet"
    closed = pd.read_parquet(closed_path)
    closed["pnl"] = [1.0 if idx % 2 == 0 else -2.0 for idx in range(len(closed))]
    closed["return_bps"] = closed["pnl"] * 10.0
    closed.to_parquet(closed_path, index=False)

    report = build_statistical_qualification(
        {"rows": [row]},
        analysis_dir=tmp_path,
        manifest_path=tmp_path / "frozen.json",
        execution_delay_bars=1,
        thresholds=_thresholds(),
    )
    reasons = report["routes"][0]["reasons"]
    assert "pf_ci_lower" in reasons
    assert "expectancy_bps_ci_lower" in reasons
    assert "mc_loss_probability" in reasons


def test_overlapping_oos_boundary_fails(tmp_path: Path) -> None:
    row = _write_route_artifacts(tmp_path, oos_trades=100)
    portfolio_path = tmp_path / "walkforward_ETHUSDT_15m_trend_portfolio.parquet"
    portfolio = pd.read_parquet(portfolio_path)
    first_oos_index = portfolio.index[portfolio["fold"] == 1][0]
    prior_end = portfolio.loc[portfolio["fold"] == 0, "timestamp"].max()
    portfolio.loc[first_oos_index, "timestamp"] = prior_end
    portfolio.to_parquet(portfolio_path, index=False)

    report = build_statistical_qualification(
        {"rows": [row]},
        analysis_dir=tmp_path,
        manifest_path=tmp_path / "frozen.json",
        execution_delay_bars=1,
        thresholds=_thresholds(),
    )
    assert "oos_boundary_separated" in report["routes"][0]["reasons"]
