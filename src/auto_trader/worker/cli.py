from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import yaml

from auto_trader.regime.classifier import RegimeConfig
from auto_trader.worker.runner import LiveTradingWorker, WorkerConfig


def _csv_text(value: str) -> tuple[str, ...]:
    text = str(value).strip()
    if not text:
        return ()
    return tuple(item.strip() for item in text.split(",") if item.strip())


def _env_bool(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value
    return default


def _env_float(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return float(text)


def _load_settings_risk(settings_path: str) -> tuple[float, float] | None:
    path = Path(settings_path).expanduser()
    if not settings_path or not path.exists():
        return None
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    risk = payload.get("risk", {}) if isinstance(payload, dict) else {}
    if not isinstance(risk, dict):
        return None
    symbol = float(risk.get("max_symbol_exposure_pct", 25.0))
    portfolio = float(risk.get("max_portfolio_exposure_pct", 70.0))
    return symbol, portfolio


def _resolve_risk_limits(
    *,
    execution_mode: str,
    settings_path: str,
    max_symbol_exposure_pct: float | None,
    max_portfolio_exposure_pct: float | None,
) -> tuple[float, float]:
    settings_risk = _load_settings_risk(settings_path)
    default_symbol = 8.0 if execution_mode == "production" else 25.0
    default_portfolio = 25.0 if execution_mode == "production" else 70.0
    symbol = max_symbol_exposure_pct if max_symbol_exposure_pct is not None else settings_risk[0] if settings_risk is not None else default_symbol
    portfolio = max_portfolio_exposure_pct if max_portfolio_exposure_pct is not None else settings_risk[1] if settings_risk is not None else default_portfolio
    return symbol, portfolio


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Live trading worker for testnet.")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--interval-sec", type=float, default=float(os.getenv("WORKER_INTERVAL_SEC", "5")))
    p.add_argument("--max-iterations", type=int, default=None)
    p.add_argument("--symbols", default=os.getenv("WORKER_SYMBOLS", "ETHUSDT,XRPUSDT,ADAUSDT"))
    p.add_argument(
        "--execution-mode",
        choices=["dry-run", "testnet", "production"],
        default=os.getenv("WORKER_EXECUTION_MODE", "testnet"),
    )
    p.add_argument("--trend-symbols", default=os.getenv("TREND_ENABLED_SYMBOLS", "ETHUSDT,XRPUSDT,ADAUSDT"))
    p.add_argument("--range-symbols", default=os.getenv("RANGE_ENABLED_SYMBOLS", "XRPUSDT"))
    p.add_argument(
        "--route-selection-path",
        default=_env_first(
            "ROUTE_SELECTION_PATH",
            "WEEKLY_REVALIDATION_REPORT_PATH",
            default="data/validation/weekly_revalidation/weekly_revalidation_report.json",
        ),
    )
    p.add_argument(
        "--weekly-revalidation-report-path",
        default=os.getenv(
            "WEEKLY_REVALIDATION_REPORT_PATH",
            "data/validation/weekly_revalidation/weekly_revalidation_report.json",
        ),
    )
    p.set_defaults(
        auto_sync_route_selection=_env_bool(
            "AUTO_SYNC_ROUTE_SELECTION",
            "1" if _env_bool("AUTO_SYNC_WEEKLY_SYMBOLS", "1") else "0",
        ),
        auto_sync_weekly_symbols=_env_bool("AUTO_SYNC_WEEKLY_SYMBOLS", "1"),
    )
    p.add_argument(
        "--auto-sync-route-selection",
        dest="auto_sync_route_selection",
        action="store_true",
    )
    p.add_argument(
        "--no-auto-sync-route-selection",
        dest="auto_sync_route_selection",
        action="store_false",
    )
    p.add_argument(
        "--auto-sync-weekly-symbols",
        dest="auto_sync_weekly_symbols",
        action="store_true",
    )
    p.add_argument(
        "--no-auto-sync-weekly-symbols",
        dest="auto_sync_weekly_symbols",
        action="store_false",
    )
    p.add_argument(
        "--trend-order-mode",
        choices=["market", "limit"],
        default=os.getenv("TREND_ORDER_MODE", "market"),
    )
    p.add_argument(
        "--range-order-mode",
        choices=["market", "limit"],
        default=os.getenv("RANGE_ORDER_MODE", "market"),
    )
    p.add_argument("--allowed-hours", default=os.getenv("ALLOWED_HOURS", ""))
    p.add_argument("--market-base-url", default=os.getenv("MARKET_BASE_URL", "https://fapi.binance.com"))
    p.add_argument("--market-klines-path", default=os.getenv("MARKET_KLINES_PATH", "/fapi/v1/klines"))
    p.add_argument("--market-interval", default=os.getenv("MARKET_INTERVAL", "1m"))
    p.add_argument("--market-limit", type=int, default=int(os.getenv("MARKET_LIMIT", "1500")))
    p.add_argument("--strategy-timeframe", default=os.getenv("STRATEGY_TIMEFRAME", "15m"))
    p.add_argument("--poll-interval-sec", type=float, default=None)
    p.add_argument("--stale-signal-ttl-sec", type=int, default=int(os.getenv("STALE_SIGNAL_TTL_SEC", "1800")))
    p.add_argument("--equity", type=float, default=float(os.getenv("WORKER_EQUITY", "1000")))
    p.add_argument("--limit-offset-rate", type=float, default=float(os.getenv("LIMIT_OFFSET_RATE", "0.0")))
    p.add_argument(
        "--runtime-state-path",
        default=os.getenv("RUNTIME_STATE_PATH", "data/runtime/control_state.json"),
    )
    p.add_argument(
        "--runtime-state-max-age-sec",
        type=int,
        default=int(os.getenv("RUNTIME_STATE_MAX_AGE_SEC", "120")),
    )
    p.add_argument(
        "--allow-runtime-state-fail-open",
        action="store_true",
        default=_env_bool("ALLOW_RUNTIME_STATE_FAIL_OPEN", "0"),
    )
    p.add_argument(
        "--gateway-state-path",
        default=os.getenv("GATEWAY_STATE_PATH", "data/exchange/gateway_state.json"),
    )
    p.add_argument("--positions-dir", default=os.getenv("POSITIONS_DIR", "data/positions"))
    p.add_argument(
        "--worker-state-path",
        default=os.getenv("WORKER_STATE_PATH", "data/runtime/worker_state.json"),
    )
    p.add_argument(
        "--order-events-path",
        default=os.getenv("ORDER_EVENTS_PATH", "data/exchange/order_events.jsonl"),
    )
    p.add_argument(
        "--execution-events-path",
        default=os.getenv("EXECUTION_EVENTS_PATH", "data/exchange/execution_events.jsonl"),
    )
    p.add_argument(
        "--execution-cursor-path",
        default=os.getenv("EXECUTION_CURSOR_PATH", "data/exchange/execution_cursor.json"),
    )
    p.add_argument("--ml-artifact-path", default=os.getenv("ML_ARTIFACT_PATH", ""))
    p.add_argument("--settings-path", default=os.getenv("SETTINGS_PATH", ""))
    p.add_argument(
        "--risk-input-path",
        default=os.getenv("RISK_INPUT_PATH", "data/risk/risk_input.parquet"),
    )
    p.add_argument(
        "--max-symbol-exposure-pct",
        type=float,
        default=_env_float("MAX_SYMBOL_EXPOSURE_PCT"),
    )
    p.add_argument(
        "--max-portfolio-exposure-pct",
        type=float,
        default=_env_float("MAX_PORTFOLIO_EXPOSURE_PCT"),
    )
    p.add_argument(
        "--high-vol-atr-zscore-threshold",
        type=float,
        default=float(os.getenv("HIGH_VOL_ATR_ZSCORE_THRESHOLD", "3.0")),
    )
    p.add_argument(
        "--high-vol-return-abs-zscore-threshold",
        type=float,
        default=float(os.getenv("HIGH_VOL_RETURN_ABS_ZSCORE_THRESHOLD", "3.0")),
    )
    p.add_argument(
        "--high-vol-sustained-min-bars",
        type=int,
        default=int(os.getenv("HIGH_VOL_SUSTAINED_MIN_BARS", "3")),
    )
    p.add_argument(
        "--min-regime-hold-bars",
        type=int,
        default=int(os.getenv("MIN_REGIME_HOLD_BARS", "1")),
    )
    p.add_argument(
        "--high-vol-cooldown-bars",
        type=int,
        default=int(os.getenv("HIGH_VOL_COOLDOWN_BARS", "1")),
    )
    return p


def main() -> int:
    args = _build_parser().parse_args()
    settings_path = str(args.settings_path).strip()
    max_symbol_exposure_pct, max_portfolio_exposure_pct = _resolve_risk_limits(
        execution_mode=args.execution_mode,
        settings_path=settings_path,
        max_symbol_exposure_pct=args.max_symbol_exposure_pct,
        max_portfolio_exposure_pct=args.max_portfolio_exposure_pct,
    )
    config = WorkerConfig(
        symbols=_csv_text(args.symbols),
        execution_mode=args.execution_mode,
        trend_symbols=_csv_text(args.trend_symbols),
        range_symbols=_csv_text(args.range_symbols),
        route_selection_path=str(args.route_selection_path).strip(),
        auto_sync_route_selection=bool(args.auto_sync_route_selection),
        weekly_revalidation_report_path=str(args.weekly_revalidation_report_path).strip(),
        auto_sync_weekly_symbols=bool(args.auto_sync_weekly_symbols),
        trend_order_mode=args.trend_order_mode,
        range_order_mode=args.range_order_mode,
        allowed_hours=str(args.allowed_hours).strip() or None,
        market_base_url=args.market_base_url,
        market_klines_path=args.market_klines_path,
        market_interval=args.market_interval,
        market_limit=args.market_limit,
        strategy_timeframe=args.strategy_timeframe,
        poll_interval_sec=(float(args.poll_interval_sec) if args.poll_interval_sec is not None else float(args.interval_sec)),
        stale_signal_ttl_sec=args.stale_signal_ttl_sec,
        equity=args.equity,
        limit_offset_rate=args.limit_offset_rate,
        runtime_state_path=args.runtime_state_path,
        runtime_state_max_age_sec=args.runtime_state_max_age_sec,
        allow_runtime_state_fail_open=bool(args.allow_runtime_state_fail_open),
        gateway_state_path=args.gateway_state_path,
        positions_dir=args.positions_dir,
        worker_state_path=args.worker_state_path,
        order_events_path=args.order_events_path,
        execution_events_path=args.execution_events_path,
        execution_cursor_path=args.execution_cursor_path,
        ml_artifact_path=str(args.ml_artifact_path).strip() or None,
        settings_path=settings_path,
        risk_input_path=str(args.risk_input_path).strip(),
        max_iterations=args.max_iterations,
        max_symbol_exposure_pct=max_symbol_exposure_pct,
        max_portfolio_exposure_pct=max_portfolio_exposure_pct,
        regime_config=RegimeConfig(
            high_vol_atr_zscore_threshold=args.high_vol_atr_zscore_threshold,
            high_vol_return_abs_zscore_threshold=args.high_vol_return_abs_zscore_threshold,
            high_vol_sustained_min_bars=args.high_vol_sustained_min_bars,
            min_regime_hold_bars=args.min_regime_hold_bars,
            high_vol_cooldown_bars=args.high_vol_cooldown_bars,
        ),
    )
    worker = LiveTradingWorker(config=config)
    if args.watch:
        count = worker.run_watch()
        print(json.dumps({"watch": True, "iterations": count}, ensure_ascii=True))
        return 0
    result = worker.run_once()
    print(json.dumps(result, ensure_ascii=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
