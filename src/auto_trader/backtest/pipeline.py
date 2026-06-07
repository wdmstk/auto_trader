from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from auto_trader.backtest.simulator import BacktestConfig, run_backtest


def _infer_ohlcv_context(path: Path) -> tuple[str, str]:
    stem = path.stem
    parts = stem.split("_")
    if len(parts) >= 2:
        symbol = parts[0].strip().upper()
        timeframe = parts[1].strip()
        if symbol and timeframe:
            return symbol, timeframe
    return "", ""


def _infer_signals_context(path: Path) -> tuple[str, str, str]:
    stem = path.stem
    if stem.endswith("_signals"):
        stem = stem[: -len("_signals")]
    parts = stem.split("_")
    if len(parts) >= 3:
        symbol = parts[0].strip().upper()
        timeframe = parts[1].strip()
        strategy = parts[2].strip()
        if symbol and timeframe and strategy:
            return symbol, timeframe, strategy
    return "", "", ""


def _write_run_metadata(
    *,
    output_dir: Path,
    ohlcv_path: Path,
    signals_path: Path,
    ml_path: Path | None,
    config: BacktestConfig | None,
) -> Path:
    symbol, timeframe = _infer_ohlcv_context(ohlcv_path)
    sig_symbol, sig_timeframe, strategy = _infer_signals_context(signals_path)
    if not symbol:
        symbol = sig_symbol
    if not timeframe:
        timeframe = sig_timeframe

    payload: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "output_dir": str(output_dir),
        "ohlcv_path": str(ohlcv_path),
        "signals_path": str(signals_path),
        "ml_path": str(ml_path) if ml_path else None,
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": strategy,
        "config": asdict(config or BacktestConfig()),
    }
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return metadata_path


def run_backtest_pipeline(
    *,
    ohlcv_path: str | Path,
    signals_path: str | Path,
    ml_path: str | Path | None = None,
    output_dir: str | Path = "data/backtest",
    config: BacktestConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    ohlcv = pd.read_parquet(ohlcv_path)
    signals = pd.read_parquet(signals_path)
    ml_df = pd.read_parquet(ml_path) if ml_path else None
    trades, portfolio, metrics = run_backtest(
        ohlcv_df=ohlcv,
        signals_df=signals,
        ml_df=ml_df,
        config=config,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    trades.to_parquet(out / "trades.parquet", index=False)
    portfolio.to_parquet(out / "portfolio.parquet", index=False)
    pd.DataFrame([metrics]).to_parquet(out / "metrics.parquet", index=False)
    _write_run_metadata(
        output_dir=out,
        ohlcv_path=Path(ohlcv_path),
        signals_path=Path(signals_path),
        ml_path=Path(ml_path) if ml_path else None,
        config=config,
    )
    return trades, portfolio, metrics
