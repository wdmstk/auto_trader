from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.backtest.simulator import BacktestConfig, run_backtest
from auto_trader.stress.scenarios import StressScenarioConfig, apply_scenario

SCENARIOS = [
    "volatility_2x",
    "flash_crash",
    "low_liquidity",
    "spread_widening",
    "api_timeout",
    "partial_fill_10pct_cancel",
    "silent_ws_stale",
]


def run_stress_tests(
    *,
    ohlcv_path: str | Path,
    signals_path: str | Path,
    ml_path: str | Path | None = None,
    backtest_cfg: BacktestConfig | None = None,
    stress_cfg: StressScenarioConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ohlcv = pd.read_parquet(ohlcv_path)
    signals = pd.read_parquet(signals_path)
    ml_df = pd.read_parquet(ml_path) if ml_path else None

    base_trades, base_pf, base_metrics = _run_single(
        ohlcv_df=ohlcv,
        signals_df=signals,
        ml_df=ml_df,
        backtest_cfg=backtest_cfg,
    )
    results = [
        {
            "scenario_name": "baseline",
            **base_metrics,
            "failure_count": 0,
            "trade_count": len(base_trades),
        }
    ]
    compare_rows: list[dict[str, object]] = []

    for scenario in SCENARIOS:
        s_ohlcv, s_signals, failures = apply_scenario(ohlcv, signals, scenario, stress_cfg)
        spread_mult = float(
            s_signals.get("stress_spread_multiplier", pd.Series([1.0], dtype=float)).iloc[0]
        )
        trades, _, metrics = _run_single(
            ohlcv_df=s_ohlcv,
            signals_df=s_signals,
            ml_df=ml_df,
            backtest_cfg=backtest_cfg,
            spread_multiplier=spread_mult,
        )
        results.append(
            {
                "scenario_name": scenario,
                **metrics,
                "failure_count": failures,
                "trade_count": len(trades),
                "stale_latency_max_sec": float(
                    pd.to_numeric(
                        s_signals.get("stale_latency_sec", pd.Series([0.0], dtype=float)),
                        errors="coerce",
                    )
                    .fillna(0.0)
                    .max()
                ),
                "stale_detect_to_stop_latency_sec": float(
                    pd.to_numeric(
                        s_signals.get(
                            "stale_detect_to_stop_latency_sec",
                            pd.Series([0.0], dtype=float),
                        ),
                        errors="coerce",
                    )
                    .fillna(0.0)
                    .max()
                ),
                "emergency_stop_triggered": bool(
                    pd.to_numeric(
                        s_signals.get("emergency_stop", pd.Series([False])),
                        errors="coerce",
                    )
                    .fillna(0.0)
                    .astype(bool)
                    .any()
                ),
            }
        )
        compare_rows.extend(
            _degradation_rows(
                scenario,
                base_metrics,
                metrics,
            )
        )

    return pd.DataFrame(results), pd.DataFrame(compare_rows)


def _run_single(
    *,
    ohlcv_df: pd.DataFrame,
    signals_df: pd.DataFrame,
    ml_df: pd.DataFrame | None,
    backtest_cfg: BacktestConfig | None,
    spread_multiplier: float = 1.0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    cfg = backtest_cfg or BacktestConfig()
    cfg_run = BacktestConfig(
        initial_cash=cfg.initial_cash,
        fee_rate=cfg.fee_rate,
        slippage_rate=cfg.slippage_rate,
        spread_rate=cfg.spread_rate * spread_multiplier,
        execution_delay_bars=cfg.execution_delay_bars,
        unit_size=cfg.unit_size,
    )
    trades, portfolio, metrics = run_backtest(
        ohlcv_df=ohlcv_df,
        signals_df=signals_df,
        ml_df=ml_df,
        config=cfg_run,
    )
    return trades, portfolio, metrics


def _degradation_rows(
    scenario_name: str,
    baseline: dict[str, float],
    stressed: dict[str, float],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key in ["PF", "MaxDD", "MonthlyPnL"]:
        base = float(baseline.get(key, 0.0))
        val = float(stressed.get(key, 0.0))
        if base == 0.0:
            deg = 0.0
        else:
            deg = ((val - base) / abs(base)) * 100.0
        rows.append(
            {
                "scenario_name": scenario_name,
                "baseline_metric": key,
                "baseline_value": base,
                "stressed_value": val,
                "degradation_pct": deg,
            }
        )
    return rows
