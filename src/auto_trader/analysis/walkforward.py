from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from auto_trader.backtest.simulator import BacktestConfig, run_backtest


@dataclass(frozen=True)
class WalkforwardConfig:
    n_folds: int = 4
    strategy: str = "range"
    symbol: str = "BTCUSDT"
    timeframe: str = "1m"
    output_dir: str | Path = "data/analysis"
    fee_rate: float = 0.0004
    slippage_rate: float = 0.0005
    spread_rate: float = 0.0003
    delay_bars: int = 1


def run_walkforward_report(
    *,
    ohlcv_path: str | Path,
    signals_path: str | Path,
    config: WalkforwardConfig | None = None,
) -> dict[str, str]:
    cfg = config or WalkforwardConfig()
    ohlcv = pd.read_parquet(ohlcv_path)
    signals = pd.read_parquet(signals_path)

    out_dir = Path(cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{cfg.symbol}_{cfg.timeframe}_{cfg.strategy}"

    ohlcv = _normalize_keys(ohlcv)
    signals = _normalize_keys(signals)
    merged = ohlcv.merge(signals, on=["symbol", "timeframe", "timestamp"], how="inner")
    merged = merged.sort_values("timestamp").reset_index(drop=True)
    if merged.empty:
        raise ValueError("walkforward input is empty after merge")

    fold_idx = _assign_folds(merged["timestamp"], cfg.n_folds)
    merged["fold"] = fold_idx

    fold_rows: list[dict[str, object]] = []
    trade_rows: list[pd.DataFrame] = []
    portfolio_rows: list[pd.DataFrame] = []

    expected_regime = "RANGE" if cfg.strategy == "range" else "TREND"
    invalid_entry = (
        merged.get("entry_signal", pd.Series(False, index=merged.index)).fillna(False).astype(bool)
    ) & (merged.get("regime", pd.Series("", index=merged.index)).astype(str) != expected_regime)

    for fold in sorted(set(fold_idx)):
        fold_df = merged[merged["fold"] == fold].copy()
        if fold_df.empty:
            continue
        market_df = fold_df[
            ["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"]
        ].copy()
        signal_cols = [
            "symbol",
            "timeframe",
            "timestamp",
            "entry_signal",
            "exit_signal",
            "pass_filter",
            "regime",
        ]
        signal_df = fold_df[signal_cols].copy()
        trades, portfolio, metrics = run_backtest(
            ohlcv_df=market_df,
            signals_df=signal_df,
            config=BacktestConfig(
                fee_rate=cfg.fee_rate,
                slippage_rate=cfg.slippage_rate,
                spread_rate=cfg.spread_rate,
                execution_delay_bars=cfg.delay_bars,
            ),
        )
        if not trades.empty:
            trades = trades.copy()
            trades["fold"] = fold
            trade_rows.append(trades)
        if not portfolio.empty:
            portfolio = portfolio.copy()
            portfolio["fold"] = fold
            portfolio_rows.append(portfolio)

        entries = signal_df[signal_df["entry_signal"].fillna(False).astype(bool)]
        fold_rows.append(
            {
                "fold": int(fold),
                "bars": int(len(fold_df)),
                "entries": int(len(entries)),
                "entries_long": int((entries["entry_signal"] == True).sum()),  # noqa: E712
                "invalid_regime_entries": int(
                    (entries["regime"].astype(str) != expected_regime).sum()
                ),
                "pf": float(metrics["PF"]),
                "expectancy": float(metrics["Expectancy"]),
                "expectancy_bps": float(metrics["ExpectancyBps"]),
                "win_rate": float(metrics["WinRate"]),
                "max_dd": float(metrics["MaxDD"]),
                "monthly_pnl": float(metrics["MonthlyPnL"]),
                "period_pnl": float(metrics["PeriodPnL"]),
                "gross_pnl_est": float(metrics["GrossPnLEst"]),
                "total_cost_est": float(metrics["TotalCostEst"]),
                "fee_cost": float(metrics["FeeCost"]),
                "impact_cost_est": float(metrics["ImpactCostEst"]),
                "closed_trades": float(metrics["ClosedTrades"]),
            }
        )

    summary = pd.DataFrame(fold_rows).sort_values("fold").reset_index(drop=True)
    trades_all = pd.concat(trade_rows, ignore_index=True) if trade_rows else pd.DataFrame()
    portfolio_all = (
        pd.concat(portfolio_rows, ignore_index=True) if portfolio_rows else pd.DataFrame()
    )

    regime_counts = (
        merged.groupby("regime", dropna=False)["timestamp"].count().rename("bars").reset_index()
        if "regime" in merged.columns
        else pd.DataFrame(columns=["regime", "bars"])
    )
    invalid_rows = merged[invalid_entry].copy()

    summary_path = out_dir / f"walkforward_{stamp}_summary.parquet"
    trades_path = out_dir / f"walkforward_{stamp}_trades.parquet"
    portfolio_path = out_dir / f"walkforward_{stamp}_portfolio.parquet"
    regime_path = out_dir / f"walkforward_{stamp}_regime_counts.parquet"
    invalid_path = out_dir / f"walkforward_{stamp}_invalid_entries.parquet"
    meta_path = out_dir / f"walkforward_{stamp}_meta.json"

    summary.to_parquet(summary_path, index=False)
    trades_all.to_parquet(trades_path, index=False)
    portfolio_all.to_parquet(portfolio_path, index=False)
    regime_counts.to_parquet(regime_path, index=False)
    invalid_rows.to_parquet(invalid_path, index=False)

    meta = {
        "symbol": cfg.symbol,
        "timeframe": cfg.timeframe,
        "strategy": cfg.strategy,
        "n_folds": cfg.n_folds,
        "expected_regime": expected_regime,
        "rows_merged": int(len(merged)),
        "output_dir": str(out_dir),
    }
    pd.Series(meta).to_json(meta_path, force_ascii=True)
    return {
        "summary_path": str(summary_path),
        "trades_path": str(trades_path),
        "portfolio_path": str(portfolio_path),
        "regime_counts_path": str(regime_path),
        "invalid_entries_path": str(invalid_path),
        "meta_path": str(meta_path),
    }


def _normalize_keys(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["symbol", "timeframe", "timestamp"]:
        if col not in out.columns:
            raise ValueError(f"missing key column: {col}")
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out


def _assign_folds(ts: pd.Series, n_folds: int) -> list[int]:
    n = len(ts)
    if n_folds <= 1 or n <= 1:
        return [0] * n
    boundaries = [int(i * n / n_folds) for i in range(n_folds + 1)]
    folds = [0] * n
    for fold in range(n_folds):
        start = boundaries[fold]
        end = boundaries[fold + 1]
        for idx in range(start, end):
            folds[idx] = fold
    return folds
