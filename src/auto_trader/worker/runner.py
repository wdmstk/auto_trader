from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd
import yaml

from auto_trader.exchange.cli import _resolve_api_credentials
from auto_trader.exchange.gateway import GatewayConfig, OrderGateway
from auto_trader.exchange.idempotency import build_client_order_id
from auto_trader.exchange.models import OrderEvent, OrderRequest
from auto_trader.exchange.rest_client import BinanceRestTransport, RestClientConfig
from auto_trader.exchange.ws_client import BinanceWsExecutionClient, ExecutionStreamEvent
from auto_trader.execution import GatewayIntegrationLayer
from auto_trader.execution.models import ReconciliationConfig
from auto_trader.features.engine import FeatureConfig, compute_features
from auto_trader.position.manager import PositionConfig, PositionManager
from auto_trader.position.models import FillEvent, PositionState, build_route_key
from auto_trader.position.store import PositionStore
from auto_trader.regime.classifier import RegimeConfig, classify_regime
from auto_trader.risk.manager import RiskConfig as LiveRiskConfig
from auto_trader.risk.manager import RiskManager, build_concentration_score
from auto_trader.stateio import FileLock, read_json_with_recovery
from auto_trader.strategy.ml_filter import apply_signal_ml_filter, resolve_ml_artifact_path
from auto_trader.strategy.range_strategy import RangeStrategyConfig, generate_range_signals
from auto_trader.strategy.session_gate import apply_session_gate
from auto_trader.strategy.trend_strategy import TrendStrategyConfig, generate_trend_signals
from auto_trader.worker.execution_sync import reconcile_execution_events_once
from auto_trader.worker.market_data import (
    BinanceKlineClient,
    BinanceKlineClientConfig,
    resample_ohlcv,
)
from auto_trader.worker.route_sync import resolve_worker_routes
from auto_trader.worker.state import WorkerState

logger = logging.getLogger(__name__)

OrderMode = Literal["market", "limit"]


@dataclass(frozen=True)
class TradeRoute:
    symbol: str
    strategy: Literal["trend", "range"]
    timeframe: str
    expected_regime: str
    candidate_status: str = "core"
    statistical_status: str = "missing"

    def route_key(self) -> str:
        return build_route_key(
            strategy=self.strategy,
            symbol=self.symbol,
            timeframe=self.timeframe,
        )

    def state_key(self) -> str:
        return self.route_key()

    def to_dict(self) -> dict[str, object]:
        route_policy = ""
        if self.statistical_status != "pass":
            route_policy = "test-only / statistical-fail"
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "timeframe": self.timeframe,
            "expected_regime": self.expected_regime,
            "candidate_status": self.candidate_status,
            "statistical_status": self.statistical_status,
            "route_policy": route_policy,
            "route_key": self.route_key(),
        }


@dataclass(frozen=True)
class WorkerConfig:
    symbols: tuple[str, ...]
    trend_symbols: tuple[str, ...]
    range_symbols: tuple[str, ...]
    execution_mode: str = "testnet"
    route_selection_path: str = ""
    auto_sync_route_selection: bool = True
    weekly_revalidation_report_path: str = "data/validation/weekly_revalidation/weekly_revalidation_report.json"
    auto_sync_weekly_symbols: bool = True
    trend_order_mode: OrderMode = "market"
    range_order_mode: OrderMode = "market"
    allowed_hours: str | None = None
    market_base_url: str = "https://fapi.binance.com"
    market_klines_path: str = "/fapi/v1/klines"
    market_interval: str = "1m"
    market_limit: int = 1500
    strategy_timeframe: str = "15m"
    poll_interval_sec: float = 5.0
    stale_signal_ttl_sec: int = 1800
    equity: float = 1000.0
    limit_offset_rate: float = 0.0
    runtime_state_path: str = "data/runtime/control_state.json"
    runtime_state_max_age_sec: int = 120
    allow_runtime_state_fail_open: bool = False
    settings_path: str = ""
    risk_input_path: str = "data/risk/risk_input.parquet"
    gateway_state_path: str = "data/exchange/gateway_state.json"
    positions_dir: str = "data/positions"
    worker_state_path: str = "data/runtime/worker_state.json"
    order_events_path: str = "data/exchange/order_events.jsonl"
    execution_events_path: str = "data/exchange/execution_events.jsonl"
    execution_cursor_path: str = "data/exchange/execution_cursor.json"
    ml_artifact_path: str | None = None
    max_iterations: int | None = None
    max_symbol_exposure_pct: float = 25.0
    max_portfolio_exposure_pct: float = 70.0
    range_strategy: RangeStrategyConfig = RangeStrategyConfig()
    trend_strategy: TrendStrategyConfig = TrendStrategyConfig()
    feature_config: FeatureConfig = FeatureConfig()
    regime_config: RegimeConfig = RegimeConfig()
    position_config: PositionConfig = PositionConfig()
    enable_execution_reconciliation: bool = False
    reconciliation_state_path: str = "data/execution/reconciliation_state.json"
    cache_enabled: bool = False
    cache_dir: str = "data/cache/market_data"
    cache_ttl_seconds: int = 60


@dataclass(frozen=True)
class ExecutionSyncState:
    status: str
    cumulative_filled_qty: float
    event_ts: datetime


@dataclass(frozen=True)
class EffectiveRiskConfig:
    source_path: str
    max_dd_pct: float
    max_symbol_exposure_pct: float
    max_portfolio_exposure_pct: float
    max_correlated_exposure_pct: float
    max_vol_weighted_exposure_pct: float
    max_risk_contribution_pct: float


@dataclass(frozen=True)
class ExecutionConfig:
    enable_reconciliation: bool = False
    reconciliation_state_path: str = "data/execution/reconciliation_state.json"


class LiveTradingWorker:
    def __init__(
        self,
        *,
        config: WorkerConfig,
        market_client: BinanceKlineClient | None = None,
        transport: object | None = None,
        sleeper: Any = time.sleep,
    ) -> None:
        self.config = config
        self._effective_risk_config = self._load_effective_risk_config()
        self._risk_manager = RiskManager(
            LiveRiskConfig(
                max_dd_pct=self._effective_risk_config.max_dd_pct,
                max_symbol_exposure_pct=self._effective_risk_config.max_symbol_exposure_pct,
                max_portfolio_exposure_pct=self._effective_risk_config.max_portfolio_exposure_pct,
                max_correlated_exposure_pct=self._effective_risk_config.max_correlated_exposure_pct,
                max_vol_weighted_exposure_pct=self._effective_risk_config.max_vol_weighted_exposure_pct,
                max_risk_contribution_pct=self._effective_risk_config.max_risk_contribution_pct,
            )
        )
        self.market_client = market_client or BinanceKlineClient(
            BinanceKlineClientConfig(
                base_url=config.market_base_url,
                klines_path=config.market_klines_path,
                cache_enabled=config.cache_enabled,
                cache_dir=config.cache_dir,
                cache_ttl_seconds=config.cache_ttl_seconds,
            )
        )
        self.sleeper = sleeper
        self._base_symbols = tuple(config.symbols)
        self._active_trend_symbols = tuple(config.trend_symbols)
        self._active_range_symbols = tuple(config.range_symbols)
        self._active_routes: dict[str, TradeRoute] = {}
        for symbol in self._active_trend_symbols:
            route = TradeRoute(
                symbol=symbol,
                strategy="trend",
                timeframe=config.strategy_timeframe,
                expected_regime="TREND",
                candidate_status="legacy",
                statistical_status="missing",
            )
            self._active_routes[route.route_key()] = route
        for symbol in self._active_range_symbols:
            route = TradeRoute(
                symbol=symbol,
                strategy="range",
                timeframe=config.strategy_timeframe,
                expected_regime="RANGE",
                candidate_status="legacy",
                statistical_status="missing",
            )
            self._active_routes.setdefault(route.route_key(), route)
        self._active_symbols = self._merge_symbols(self._base_symbols, self._active_trend_symbols, self._active_range_symbols)
        self.position_store = PositionStore(config.positions_dir)
        position_config = PositionConfig(
            max_add_count=config.position_config.max_add_count,
            max_symbol_exposure_pct=self._effective_risk_config.max_symbol_exposure_pct,
            max_portfolio_exposure_pct=self._effective_risk_config.max_portfolio_exposure_pct,
        )
        self.position_manager = PositionManager(position_config)
        self.position_manager.replace_positions(self.position_store.load())
        self.worker_state = self._load_worker_state()
        self.execution_client = BinanceWsExecutionClient()
        self.gateway = self._build_gateway(transport=transport)

        # Load execution configuration from settings
        exec_config = self._load_execution_config()

        # Initialize ExecutionReconciler if enabled
        self.execution_integration_layer: GatewayIntegrationLayer | None = None
        if exec_config.enable_reconciliation:
            recon_config = ReconciliationConfig(
                reconciliation_interval_sec=30,
                event_cache_size=10000,
                alert_on_mismatch=True,
            )
            self.execution_integration_layer = GatewayIntegrationLayer(
                gateway=self.gateway,
                config=recon_config,
                fill_event_callback=self._handle_reconciler_fill_event,
                state_path=exec_config.reconciliation_state_path,
            )
            logger.info("ExecutionReconciler enabled and initialized")
        else:
            logger.info("ExecutionReconciler disabled (using legacy flow)")

    def run_watch(self) -> int:
        iterations = 0
        while True:
            self.run_once()
            iterations += 1
            if self.config.max_iterations is not None and iterations >= self.config.max_iterations:
                return iterations
            self.sleeper(max(self.config.poll_interval_sec, 0.1))

    def run_once(self) -> dict[str, object]:
        runtime_state = self._read_runtime_state()
        symbol_sync = self._refresh_symbols_from_route_selection()
        cycle_started_at = _now_iso()
        orders: list[dict[str, object]] = []
        symbols: dict[str, dict[str, object]] = {}
        routes: dict[str, dict[str, object]] = {}
        summary: dict[str, object] = {
            "cycle_started_at": cycle_started_at,
            "orders": orders,
            "symbols": symbols,
            "routes": routes,
            "runtime": runtime_state,
            "symbol_sync": symbol_sync,
            "execution_sync": self.reconcile_execution_events_once(),
            "effective_config": {
                "risk": {
                    "source_path": self._effective_risk_config.source_path,
                    "max_dd_pct": self._effective_risk_config.max_dd_pct,
                    "max_symbol_exposure_pct": self._effective_risk_config.max_symbol_exposure_pct,
                    "max_portfolio_exposure_pct": self._effective_risk_config.max_portfolio_exposure_pct,
                    "max_correlated_exposure_pct": self._effective_risk_config.max_correlated_exposure_pct,
                    "max_vol_weighted_exposure_pct": self._effective_risk_config.max_vol_weighted_exposure_pct,
                    "max_risk_contribution_pct": self._effective_risk_config.max_risk_contribution_pct,
                }
            },
            "trade_symbols": {
                "symbols": list(self._active_symbols),
                "trend_symbols": list(self._active_trend_symbols),
                "range_symbols": list(self._active_range_symbols),
                "trade_routes": [route.to_dict() for route in self._active_routes.values()],
            },
            "cache_metrics": self.market_client.get_cache_metrics(),
        }
        mark_prices: dict[str, float] = {}
        try:
            closed_by_symbol = self._load_closed_market_frames()
            mark_prices = {symbol: float(frame["close"].iloc[-1]) for symbol, frame in closed_by_symbol.items() if not frame.empty}
        except Exception as exc:
            self.worker_state.last_error = f"market_data_error:{exc.__class__.__name__}"
            self.worker_state.last_cycle_at = cycle_started_at
            self.worker_state.updated_at = _now_iso()
            self.worker_state.save(self.config.worker_state_path)
            return summary

        if runtime_state["emergency_stop"] or runtime_state["close_all_requested"]:
            flattened = self._flatten_positions(mark_prices, reason="emergency_close")
            orders.extend(flattened)
            self._persist_cycle(summary, cycle_started_at)
            return summary

        if not runtime_state["trading_enabled"]:
            self._persist_cycle(summary, cycle_started_at)
            return summary

        for route_key, route in self._active_routes.items():
            route_summary: dict[str, object] = {"status": "skipped", "route": route.to_dict()}
            raw_frame = closed_by_symbol.get(route.symbol)
            if raw_frame is None or raw_frame.empty:
                route_summary["status"] = "missing_data"
                routes[route_key] = route_summary
                continue

            frame = self._closed_market_frame(raw_frame, route.timeframe)
            if frame.empty:
                route_summary["status"] = "missing_data"
                routes[route_key] = route_summary
                continue
            latest_bar_ts = str(pd.to_datetime(frame["timestamp"].iloc[-1], utc=True))
            mark_price = float(raw_frame["close"].iloc[-1])
            mark_prices[route.symbol] = mark_price

            state_key = route.state_key()
            already_processed = self.worker_state.last_processed_bars.get(state_key) == latest_bar_ts
            signal_frame = self._build_signal_frame(
                symbol=route.symbol,
                frame_15m=frame,
                route=route.strategy,
                timeframe=route.timeframe,
            )
            if signal_frame is None or signal_frame.empty:
                self.worker_state.last_processed_bars[state_key] = latest_bar_ts
                route_summary["status"] = "no_signal"
                routes[route_key] = route_summary
                continue

            latest = cast(dict[str, object], signal_frame.iloc[-1].to_dict())
            route_summary["signal"] = {
                "timestamp": str(latest.get("timestamp", "")),
                "regime": str(latest.get("regime", "")),
                "expected_regime": route.expected_regime,
                "timeframe": route.timeframe,
                "entry_signal": bool(latest.get("entry_signal", False)),
                "exit_signal": bool(latest.get("exit_signal", False)),
                "add_signal": bool(latest.get("add_signal", False)),
                "pass_filter": bool(latest.get("pass_filter", False)),
                "reason_codes": latest.get("signal_reason_codes", []),
            }
            pos = self.position_manager.get(route_key)
            self.worker_state.last_processed_bars[state_key] = latest_bar_ts
            if already_processed:
                route_summary["status"] = "already_processed"
                route_summary["trade"] = {
                    "order_submitted": False,
                    "status": "already_processed",
                }
            else:
                action_result = self._maybe_trade(
                    route=route,
                    latest_row=latest,
                    position=pos,
                    mark_price=mark_price,
                    mark_prices=mark_prices,
                    allow_runtime_gate=False,
                )
                route_summary["risk_blocked"] = bool(action_result.get("risk_blocked", False))
                if "risk" in action_result:
                    route_summary["risk"] = action_result.get("risk")
                route_summary["trade"] = action_result
                if action_result.get("order_submitted"):
                    orders.append(action_result)
            routes[route_key] = route_summary

        for route in self._active_routes.values():
            symbol_summary: dict[str, object] = symbols.setdefault(
                route.symbol,
                {"status": "ready", "active_route_count": 0, "routes": []},
            )
            symbol_routes = symbol_summary.get("routes")
            if isinstance(symbol_routes, list):
                route_result = routes.get(route.route_key(), {})
                if isinstance(route_result, dict):
                    symbol_routes.append(route_result)
            active_route_count = symbol_summary.get("active_route_count", 0)
            symbol_summary["active_route_count"] = (int(active_route_count) if isinstance(active_route_count, int | str) else 0) + 1
            if route.route_key() in routes:
                route_result = routes[route.route_key()]
                symbol_summary["status"] = str(route_result.get("status", symbol_summary["status"]))

        self._persist_cycle(summary, cycle_started_at)
        return summary

    def _persist_cycle(self, summary: dict[str, object], cycle_started_at: str) -> None:
        self.worker_state.last_cycle_at = cycle_started_at
        results_obj = summary.get("routes", summary.get("symbols", {}))
        if isinstance(results_obj, dict):
            self.worker_state.last_results = {
                str(symbol): cast(dict[str, object], result) for symbol, result in results_obj.items() if isinstance(result, dict)
            }
        else:
            self.worker_state.last_results = {}
        self.worker_state.last_error = ""
        self.worker_state.updated_at = _now_iso()
        self.worker_state.save(self.config.worker_state_path)
        self.position_store.save(self.position_manager.all_positions())

    def _flatten_positions(self, mark_prices: dict[str, float], *, reason: str) -> list[dict[str, object]]:
        orders: list[dict[str, object]] = []
        for pos in list(self.position_manager.all_positions()):
            if pos.qty <= 0:
                continue
            price = mark_prices.get(pos.symbol, pos.avg_entry)
            submitted = self._submit_order(
                symbol=pos.symbol,
                side="sell" if pos.side == "buy" else "buy",
                qty=pos.qty,
                order_type="market",
                limit_price=None,
                signal_ts=datetime.now(UTC),
                regime="HIGH_VOL",
                pass_filter=True,
                strategy=pos.strategy,
                timeframe=pos.timeframe,
                route_key=pos.route_key,
                allow_runtime_gate=True,
                action="emergency_close",
                price=price,
                is_add=False,
                pre_position=pos,
            )
            submitted["reason"] = reason
            orders.append(submitted)
        return orders

    def _maybe_trade(
        self,
        *,
        route: TradeRoute,
        latest_row: dict[str, object],
        position: PositionState | None,
        mark_price: float,
        mark_prices: dict[str, float],
        allow_runtime_gate: bool,
    ) -> dict[str, object]:
        signal_ts = pd.to_datetime(cast(Any, latest_row.get("timestamp")), utc=True).to_pydatetime()
        regime = str(latest_row.get("regime", ""))
        pass_filter = bool(latest_row.get("pass_filter", False))
        entry_signal = bool(latest_row.get("entry_signal", False))
        exit_signal = bool(latest_row.get("exit_signal", False))
        add_signal = bool(latest_row.get("add_signal", False))
        size_ratio = float(cast(Any, latest_row.get("position_size_ratio", 0.0)))
        reason_codes_value = latest_row.get("signal_reason_codes", [])
        reason_codes = reason_codes_value if isinstance(reason_codes_value, list) else []
        order_mode = self.config.trend_order_mode if route.strategy == "trend" else self.config.range_order_mode
        if route.strategy == "trend" and route.symbol not in self._active_trend_symbols:
            return {"order_submitted": False, "status": "disabled"}
        if route.strategy == "range" and route.symbol not in self._active_range_symbols:
            return {"order_submitted": False, "status": "disabled"}

        if position is not None and exit_signal:
            qty = float(position.qty)
            if qty <= 0:
                return {"order_submitted": False, "status": "no_position"}
            return self._submit_order(
                symbol=route.symbol,
                side="sell" if position.side == "buy" else "buy",
                qty=qty,
                order_type=order_mode,
                limit_price=self._limit_price(order_mode, mark_price, "sell" if position.side == "buy" else "buy"),
                signal_ts=signal_ts,
                regime=regime,
                pass_filter=pass_filter,
                strategy=route.strategy,
                timeframe=route.timeframe,
                route_key=route.route_key(),
                allow_runtime_gate=allow_runtime_gate,
                action="exit",
                price=mark_price,
                is_add=False,
                reason_codes=reason_codes,
                pre_position=position,
            )

        if position is None and entry_signal and pass_filter:
            qty = self._entry_qty(mark_price, size_ratio)
            if qty <= 0:
                return {"order_submitted": False, "status": "qty_zero"}
            risk_eval = self._evaluate_projected_risk(
                route=route,
                side="buy",
                qty=qty,
                mark_price=mark_price,
                mark_prices=mark_prices,
            )
            if bool(risk_eval.get("risk_blocked", False)):
                return {
                    "order_submitted": False,
                    "status": "risk_blocked",
                    "risk_blocked": True,
                    "risk": risk_eval,
                }
            return self._submit_order(
                symbol=route.symbol,
                side="buy",
                qty=qty,
                order_type=order_mode,
                limit_price=self._limit_price(order_mode, mark_price, "buy"),
                signal_ts=signal_ts,
                regime=regime,
                pass_filter=pass_filter,
                strategy=route.strategy,
                timeframe=route.timeframe,
                route_key=route.route_key(),
                allow_runtime_gate=allow_runtime_gate,
                action="entry",
                price=mark_price,
                is_add=False,
                reason_codes=reason_codes,
                pre_position=None,
                risk_eval=risk_eval,
            )

        if position is not None and add_signal and pass_filter:
            qty = self._entry_qty(mark_price, size_ratio)
            if qty <= 0:
                return {"order_submitted": False, "status": "qty_zero"}
            risk_eval = self._evaluate_projected_risk(
                route=route,
                side="buy",
                qty=qty,
                mark_price=mark_price,
                mark_prices=mark_prices,
            )
            if bool(risk_eval.get("risk_blocked", False)):
                return {
                    "order_submitted": False,
                    "status": "risk_blocked",
                    "risk_blocked": True,
                    "risk": risk_eval,
                }
            return self._submit_order(
                symbol=route.symbol,
                side="buy",
                qty=qty,
                order_type=order_mode,
                limit_price=self._limit_price(order_mode, mark_price, "buy"),
                signal_ts=signal_ts,
                regime=regime,
                pass_filter=pass_filter,
                strategy=route.strategy,
                timeframe=route.timeframe,
                route_key=route.route_key(),
                allow_runtime_gate=allow_runtime_gate,
                action="add",
                price=mark_price,
                is_add=True,
                reason_codes=reason_codes,
                pre_position=position,
                risk_eval=risk_eval,
            )

        return {"order_submitted": False, "status": "no_action", "risk_blocked": False}

    def _submit_order(
        self,
        *,
        symbol: str,
        side: Literal["buy", "sell"],
        qty: float,
        order_type: OrderMode,
        limit_price: float | None,
        signal_ts: datetime,
        regime: str,
        pass_filter: bool,
        strategy: str,
        timeframe: str,
        route_key: str,
        allow_runtime_gate: bool,
        action: str,
        price: float,
        is_add: bool,
        reason_codes: object | None = None,
        pre_position: PositionState | None = None,
        risk_eval: dict[str, object] | None = None,
    ) -> dict[str, object]:
        normalized_qty = float(qty)
        normalized_limit_price = limit_price
        if hasattr(self.gateway.transport, "normalize_order_request"):
            normalized = self.gateway.transport.normalize_order_request(
                OrderRequest(
                    symbol=symbol,
                    side=side,
                    qty=float(qty),
                    signal_ts=signal_ts,
                    regime=regime,
                    pass_filter=bool(pass_filter),
                    client_order_id="preview",
                    order_type=order_type,
                    limit_price=limit_price,
                )
            )
            normalized_qty = float(normalized.qty)
            normalized_limit_price = normalized.limit_price
        cid = build_client_order_id(
            symbol=symbol,
            side=side,
            signal_ts=signal_ts,
            strategy=strategy,
            nonce=timeframe,
        )
        req = OrderRequest(
            symbol=symbol,
            side=side,
            qty=normalized_qty,
            signal_ts=signal_ts,
            regime=regime,
            pass_filter=bool(pass_filter),
            client_order_id=cid,
            order_type=order_type,
            limit_price=normalized_limit_price,
        )
        # Use ExecutionReconciler if enabled
        if self.execution_integration_layer is not None:
            event, fill_event = self.execution_integration_layer.submit_with_reconciliation(
                req,
                allow_runtime_gate=allow_runtime_gate,
                allow_policy_gate=allow_runtime_gate or action in {"exit", "emergency_close"},
            )
            # FillEvent is handled via callback, so we don't process it here
        else:
            event = self.gateway.submit(
                req,
                allow_runtime_gate=allow_runtime_gate,
                allow_policy_gate=allow_runtime_gate or action in {"exit", "emergency_close"},
            )
        block_reason_codes = []
        if isinstance(risk_eval, dict):
            raw_block_reason_codes = risk_eval.get("block_reason_codes", [])
            if isinstance(raw_block_reason_codes, list):
                block_reason_codes = [str(value) for value in raw_block_reason_codes]
        log_row = {
            "ts": _now_iso(),
            "symbol": symbol,
            "side": side,
            "strategy": strategy,
            "timeframe": timeframe,
            "route_key": route_key,
            "action": action,
            "order_type": order_type,
            "order_id": event.order_id,
            "client_order_id": event.client_order_id,
            "status": event.status,
            "reason": event.reason,
            "qty": event.qty,
            "requested_at": event.requested_at.isoformat(),
            "sent_at": event.sent_at.isoformat() if event.sent_at else "",
            "ack_at": event.ack_at.isoformat() if event.ack_at else "",
            "latency_ms": event.latency_ms,
            "limit_price": event.limit_price,
            "price": float(price),
            "signal_ts": signal_ts.isoformat(),
            "regime": regime,
            "reason_codes": reason_codes if reason_codes is not None else [],
            "pre_position_exists": pre_position is not None and pre_position.qty > 0.0,
            "pre_position_qty": float(pre_position.qty) if pre_position is not None else 0.0,
            "pre_position_avg_entry": (float(pre_position.avg_entry) if pre_position is not None else 0.0),
            "pre_position_side": pre_position.side if pre_position is not None else "",
            "pre_position_add_count": int(pre_position.add_count) if pre_position is not None else 0,
            "risk_blocked": bool((risk_eval or {}).get("risk_blocked", False)),
            "risk_codes": block_reason_codes,
            "risk_size_scale": _coerce_float(
                risk_eval.get("size_scale", 1.0) if isinstance(risk_eval, dict) else 1.0,
                default=1.0,
            ),
        }
        self._append_order_event(log_row)

        result = dict(log_row)
        result["order_submitted"] = True
        result["gateway_status"] = event.status
        result["gateway_reason"] = event.reason
        result["risk"] = risk_eval or {"risk_blocked": False, "block_reason_codes": ["RISK_OK"]}
        if event.status == "ack":
            result["pending_reconciliation"] = True
        return result

    def _append_order_event(self, payload: dict[str, object]) -> None:
        path = Path(self.config.order_events_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_suffix(f"{path.suffix}.lock")
        with FileLock(lock_path, timeout_sec=1.0):
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=True) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def reconcile_execution_events_once(self) -> dict[str, object]:
        return reconcile_execution_events_once(
            events_path=self.config.execution_events_path,
            cursor_path=self.config.execution_cursor_path,
            parse_message=self.execution_client.parse_message,
            handle_event=self._apply_execution_event,
        )

    def _apply_execution_event(self, event: ExecutionStreamEvent) -> bool:
        order_row = self._find_order_event_context(
            order_id=event.order_id,
            client_order_id=event.client_order_id,
        )
        if order_row is None:
            return False

        route_key = str(order_row.get("route_key", "")).strip()
        if not route_key:
            return False

        previous_sync = self._last_execution_sync_state(
            order_id=event.order_id,
            client_order_id=event.client_order_id,
        )
        cumulative_filled_qty = max(float(event.filled_qty), 0.0)
        previous_cumulative = previous_sync.cumulative_filled_qty if previous_sync is not None else 0.0
        if cumulative_filled_qty < previous_cumulative:
            return False
        if previous_sync is not None and cumulative_filled_qty == previous_cumulative and event.status == previous_sync.status:
            return False
        if previous_sync is not None and cumulative_filled_qty <= previous_cumulative and event.event_ts <= previous_sync.event_ts:
            return False

        delta_filled_qty = max(0.0, cumulative_filled_qty - previous_cumulative)

        # Use ExecutionReconciler if enabled
        if self.execution_integration_layer is not None:
            # Convert ExecutionStreamEvent to OrderEvent
            order_event = self._convert_execution_stream_to_order_event(event, order_row)
            # Process through reconciler (FillEvent is handled via callback)
            _ = self.execution_integration_layer.process_existing_order_event(order_event)
            # FillEvent is handled via callback, position is updated there
            # For tracking purposes, we use current position or None
            current_position = self.position_manager.get(route_key)
            reconciled = current_position
        else:
            # Use traditional flow
            reconciled = self._apply_execution_fill_delta(
                order_row=order_row,
                event=event,
                delta_filled_qty=delta_filled_qty,
            )
        if reconciled is None or reconciled.qty <= 0.0:
            self.position_manager.remove_position(route_key)
            reconciled_qty = 0.0
        else:
            self.position_manager.set_position(reconciled)
            reconciled_qty = float(reconciled.qty)
        self.position_store.save(self.position_manager.all_positions())

        sync_row = {
            "ts": _now_iso(),
            "symbol": str(order_row.get("symbol", "")),
            "side": str(order_row.get("side", "")),
            "strategy": str(order_row.get("strategy", "")),
            "timeframe": str(order_row.get("timeframe", "")),
            "route_key": route_key,
            "action": str(order_row.get("action", "")),
            "order_type": str(order_row.get("order_type", "market")),
            "order_id": event.order_id,
            "client_order_id": event.client_order_id,
            "status": event.status,
            "reason": "execution_report_sync",
            "qty": _coerce_float(order_row.get("qty", 0.0) or 0.0),
            "requested_at": str(order_row.get("requested_at", "")),
            "sent_at": str(order_row.get("sent_at", "")),
            "ack_at": str(order_row.get("ack_at", "")),
            "latency_ms": order_row.get("latency_ms"),
            "limit_price": order_row.get("limit_price"),
            "price": _coerce_float(order_row.get("price", 0.0) or 0.0),
            "signal_ts": str(order_row.get("signal_ts", "")),
            "regime": str(order_row.get("regime", "")),
            "reason_codes": order_row.get("reason_codes", []),
            "sync_source": "execution_report",
            "execution_event_ts": event.event_ts.isoformat(),
            "execution_filled_qty": cumulative_filled_qty,
            "execution_delta_filled_qty": delta_filled_qty,
            "execution_fill_price": (float(event.avg_fill_price) if float(event.avg_fill_price) > 0.0 else _fill_price_from_order_row(order_row)),
            "reconciled_position_qty": reconciled_qty,
        }
        self._append_order_event(sync_row)
        return True

    def _last_execution_sync_state(
        self,
        *,
        order_id: str,
        client_order_id: str,
    ) -> ExecutionSyncState | None:
        path = Path(self.config.order_events_path)
        if not path.exists():
            return None
        latest: ExecutionSyncState | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if str(payload.get("sync_source", "")) != "execution_report":
                continue
            payload_order_id = str(payload.get("order_id", ""))
            payload_client_order_id = str(payload.get("client_order_id", ""))
            if order_id and payload_order_id != order_id:
                continue
            if not order_id and client_order_id and payload_client_order_id != client_order_id:
                continue
            event_ts = pd.to_datetime(
                cast(Any, payload.get("execution_event_ts", "")),
                utc=True,
                errors="coerce",
            )
            if pd.isna(event_ts):
                continue
            current = ExecutionSyncState(
                status=str(payload.get("status", "")).strip(),
                cumulative_filled_qty=_coerce_float(payload.get("execution_filled_qty", 0.0) or 0.0),
                event_ts=event_ts.to_pydatetime(),
            )
            if latest is None or current.event_ts >= latest.event_ts:
                latest = current
        return latest

    def _find_order_event_context(
        self,
        *,
        order_id: str,
        client_order_id: str,
    ) -> dict[str, object] | None:
        path = Path(self.config.order_events_path)
        if not path.exists():
            return None
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if str(payload.get("sync_source", "")) == "execution_report":
                continue
            payload_order_id = str(payload.get("order_id", ""))
            payload_client_order_id = str(payload.get("client_order_id", ""))
            if order_id and payload_order_id == order_id:
                return payload
            if client_order_id and payload_client_order_id == client_order_id:
                return payload
        return None

    def _apply_execution_fill_delta(
        self,
        order_row: dict[str, object],
        event: ExecutionStreamEvent,
        delta_filled_qty: float,
    ) -> PositionState | None:
        route_key = str(order_row.get("route_key", "")).strip()
        current_position = self.position_manager.get(route_key) or _position_from_order_row(order_row)
        if delta_filled_qty <= 0.0:
            return current_position
        side = str(order_row.get("side", "")).strip().lower()
        if side not in {"buy", "sell"}:
            return current_position

        pm = PositionManager(self.position_manager.config)
        if current_position is not None and current_position.qty > 0.0:
            pm.replace_positions([current_position])
        return pm.apply_fill(
            FillEvent(
                symbol=str(order_row.get("symbol", "")),
                side=cast(Literal["buy", "sell"], side),
                qty=delta_filled_qty,
                price=_fill_price_from_execution_event(event, order_row),
                filled_at=event.event_ts,
                is_add=str(order_row.get("action", "")).strip().lower() == "add",
                strategy=str(order_row.get("strategy", "")).strip() or "legacy",
                timeframe=str(order_row.get("timeframe", "")).strip() or "15m",
                route_key=route_key,
            )
        )

    def _handle_reconciler_fill_event(self, fill_event: FillEvent) -> None:
        """Handle FillEvent generated by ExecutionReconciler."""
        try:
            self.position_manager.apply_fill(fill_event)
            self.position_store.save(self.position_manager.all_positions())
            logger.info(f"Applied reconciler FillEvent: {fill_event.route_key} qty={fill_event.qty} price={fill_event.price}")
        except Exception as exc:
            logger.error(f"Failed to apply reconciler FillEvent: {exc}")

    def _convert_execution_stream_to_order_event(self, event: ExecutionStreamEvent, order_row: dict[str, object]) -> OrderEvent:
        """
        Convert WebSocket ExecutionStreamEvent to Gateway OrderEvent.

        Args:
            event: WebSocket execution event
            order_row: Order metadata from order events log

        Returns:
            OrderEvent for processing by ExecutionReconciler
        """
        # Map ExecutionStreamEvent status to OrderEvent status
        # ExecutionStreamEvent status: new, partially_filled, filled, canceled, rejected, etc.
        # OrderEvent status: created, sent, ack, partial_filled, filled, rejected, canceled
        status_mapping: dict[str, str] = {
            "new": "created",
            "partially_filled": "partial_filled",
            "filled": "filled",
            "canceled": "canceled",
            "rejected": "rejected",
            "expired": "canceled",
        }
        mapped_status = status_mapping.get(event.status, "created")

        # Extract order metadata
        qty = cast(float, order_row.get("qty", 0.0) or 0.0)
        # For execution events, use the filled_qty from the event for accuracy
        # This is important for partial fills
        if event.status in {"partially_filled", "filled"}:
            qty = event.filled_qty
        side = str(order_row.get("side", "")).strip().lower() or event.side
        order_type = str(order_row.get("order_type", "")).strip().lower() or "market"
        limit_price = None
        if order_row.get("limit_price") is not None:
            try:
                limit_price = float(order_row["limit_price"])  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit_price = None

        # Create OrderEvent
        return OrderEvent(
            order_id=event.order_id,
            client_order_id=event.client_order_id,
            symbol=event.symbol,
            side=cast(Literal["buy", "sell"], side),
            qty=qty,
            status=cast(Literal["created", "sent", "ack", "partial_filled", "filled", "rejected", "canceled"], mapped_status),
            reason=f"ws_update:{event.status}",
            requested_at=event.event_ts,
            sent_at=event.event_ts,
            ack_at=event.event_ts if mapped_status in {"ack", "partial_filled", "filled"} else None,
            filled_at=event.event_ts if mapped_status in {"partial_filled", "filled"} else None,
            latency_ms=None,
            order_type=cast(Literal["market", "limit"], order_type),
            limit_price=limit_price,
        )

    def _limit_price(self, order_mode: OrderMode, mark_price: float, side: str) -> float | None:
        if order_mode != "limit":
            return None
        offset = abs(float(self.config.limit_offset_rate))
        if side == "buy":
            return round(mark_price * (1.0 - offset), 6)
        return round(mark_price * (1.0 + offset), 6)

    def _entry_qty(self, mark_price: float, size_ratio: float) -> float:
        ratio = max(0.0, float(size_ratio))
        if mark_price <= 0.0 or ratio <= 0.0:
            return 0.0
        qty = (self.config.equity * ratio) / mark_price
        return round(max(qty, 0.001), 6)

    def _build_signal_frame(
        self,
        *,
        symbol: str,
        frame_15m: pd.DataFrame,
        route: Literal["trend", "range"],
        timeframe: str,
    ) -> pd.DataFrame | None:
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if frame_15m.empty or not required.issubset(frame_15m.columns):
            return None
        base = frame_15m.copy().reset_index(drop=True)
        base["symbol"] = symbol
        base["timeframe"] = timeframe
        features = compute_features(base, config=self.config.feature_config)
        regime = classify_regime(features, config=self.config.regime_config)
        if route == "range":
            signals: pd.DataFrame = generate_range_signals(
                features_df=features,
                regime_df=regime,
                config=self.config.range_strategy,
            )
        else:
            signals = generate_trend_signals(
                features_df=features,
                regime_df=regime,
                config=self.config.trend_strategy,
            )

        if self.config.allowed_hours:
            signals = apply_session_gate(signals, allowed_hours=self.config.allowed_hours)

        ml_artifact_path = resolve_ml_artifact_path(self.config.ml_artifact_path)
        if ml_artifact_path:
            try:
                signals = apply_signal_ml_filter(
                    features_df=features,
                    regime_df=regime,
                    signals_df=signals,
                    artifact_path=ml_artifact_path,
                )
            except Exception as exc:
                logger.error("ml_filter failed for %s/%s: %s", symbol, timeframe, exc, exc_info=True)
                self.worker_state.last_error = f"ml_filter_error:{exc.__class__.__name__}"
                return None
        closed_cutoff = pd.to_datetime(base["timestamp"].iloc[-1], utc=True).floor(_pandas_timeframe_rule(timeframe))
        return cast(
            pd.DataFrame,
            signals[pd.to_datetime(cast(Any, signals["timestamp"]), utc=True) <= closed_cutoff].copy(),
        )

    def _load_closed_market_frames(self) -> dict[str, pd.DataFrame]:
        closed_frames: dict[str, pd.DataFrame] = {}
        for symbol in self._active_symbols:
            raw = self.market_client.fetch_klines(
                symbol,
                interval=self.config.market_interval,
                limit=self.config.market_limit,
            )
            if raw.empty:
                continue
            raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
            closed_frames[symbol] = raw.sort_values("timestamp").reset_index(drop=True)
        return closed_frames

    def _closed_market_frame(self, raw_frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        if raw_frame.empty:
            return pd.DataFrame()
        frame = raw_frame.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.sort_values("timestamp")
        cutoff = pd.to_datetime(frame["timestamp"].iloc[-1], utc=True).floor(_pandas_timeframe_rule(timeframe))
        resampled = resample_ohlcv(frame, timeframe)
        resampled["timestamp"] = pd.to_datetime(resampled["timestamp"], utc=True)
        closed = resampled[resampled["timestamp"] <= cutoff].copy().reset_index(drop=True)
        if not closed.empty:
            closed["timeframe"] = timeframe
        return cast(pd.DataFrame, closed)

    def _read_runtime_state(self) -> dict[str, object]:
        payload = read_json_with_recovery(self.config.runtime_state_path)
        return {
            "trading_enabled": bool(payload.get("trading_enabled", False)),
            "emergency_stop": bool(payload.get("emergency_stop", False)),
            "close_all_requested": bool(payload.get("close_all_requested", False)),
            "updated_at": str(payload.get("updated_at", "")),
        }

    def _load_worker_state(self) -> WorkerState:
        path = Path(self.config.worker_state_path)
        if not path.exists():
            return WorkerState()
        try:
            return WorkerState.load(path)
        except Exception:
            logger.warning("worker_state corrupt at %s, resetting", path, exc_info=True)
            return WorkerState()

    def _latest_risk_input_rows(self) -> pd.DataFrame:
        path = Path(self.config.risk_input_path)
        if not path.exists():
            return pd.DataFrame()
        try:
            frame = pd.read_parquet(path)
        except Exception:
            logger.warning("risk_input unreadable at %s", path, exc_info=True)
            return pd.DataFrame()
        if frame.empty or "symbol" not in frame.columns:
            return pd.DataFrame()
        if "timestamp" in frame.columns:
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
            frame = frame.sort_values("timestamp")
        return frame.groupby("symbol", dropna=False).tail(1).reset_index(drop=True)

    def _evaluate_projected_risk(
        self,
        *,
        route: TradeRoute,
        side: Literal["buy", "sell"],
        qty: float,
        mark_price: float,
        mark_prices: dict[str, float],
    ) -> dict[str, object]:
        exposures = self.position_manager.exposure_snapshot(
            mark_prices=mark_prices,
            equity=self.config.equity,
        )
        projected_exposures = dict(exposures)
        additional_notional = max(float(qty), 0.0) * max(float(mark_price), 0.0)
        symbol_key = f"{route.symbol}_exposure_pct"
        projected_symbol_exposure_pct = projected_exposures.get(symbol_key, 0.0) + (
            (additional_notional / self.config.equity) * 100.0 if self.config.equity > 0 else 0.0
        )
        projected_exposures[symbol_key] = projected_symbol_exposure_pct
        projected_portfolio_exposure_pct = projected_exposures.get("portfolio_exposure_pct", 0.0) + (
            (additional_notional / self.config.equity) * 100.0 if self.config.equity > 0 else 0.0
        )
        projected_exposures["portfolio_exposure_pct"] = projected_portfolio_exposure_pct

        symbol_only_exposures = {
            key: float(value) for key, value in projected_exposures.items() if key.endswith("_exposure_pct") and key != "portfolio_exposure_pct"
        }
        concentration_score = build_concentration_score(symbol_only_exposures)
        correlated_exposure_pct = sum(sorted(symbol_only_exposures.values(), reverse=True)[:2])

        if self._normalized_execution_mode() != "production":
            risk_blocked = (
                projected_symbol_exposure_pct > self._effective_risk_config.max_symbol_exposure_pct
                or projected_portfolio_exposure_pct > self._effective_risk_config.max_portfolio_exposure_pct
            )
            codes = ["RISK_OK"]
            if risk_blocked:
                codes = []
                if projected_symbol_exposure_pct > self._effective_risk_config.max_symbol_exposure_pct:
                    codes.append("RISK_SYMBOL_EXPOSURE")
                if projected_portfolio_exposure_pct > self._effective_risk_config.max_portfolio_exposure_pct:
                    codes.append("RISK_PORTFOLIO_EXPOSURE")
            return {
                "timestamp": datetime.now(UTC).isoformat(),
                "symbol": route.symbol,
                "risk_blocked": risk_blocked,
                "block_reason_codes": codes,
                "current_dd_pct": 0.0,
                "portfolio_exposure_pct": projected_portfolio_exposure_pct,
                "concentration_score": concentration_score,
                "correlated_exposure_pct": correlated_exposure_pct,
                "vol_weighted_exposure_pct": 0.0,
                "risk_contribution_pct": 0.0,
                "missing_vol_ratio": 0.0,
                "size_scale": 0.0 if risk_blocked else 1.0,
                "emergency_state": False,
            }

        risk_input = self._latest_risk_input_rows()
        row = (
            risk_input[risk_input["symbol"].astype(str) == route.symbol].tail(1) if not risk_input.empty and "symbol" in risk_input.columns else pd.DataFrame()
        )
        current_equity = float(row.iloc[0]["current_equity"]) if not row.empty and "current_equity" in row.columns else self.config.equity
        equity_peak = float(row.iloc[0]["equity_peak"]) if not row.empty and "equity_peak" in row.columns else current_equity
        vol_weighted_exposure_pct = (
            float(row.iloc[0]["vol_weighted_exposure_pct"])
            if not row.empty and "vol_weighted_exposure_pct" in row.columns
            else projected_portfolio_exposure_pct
        )
        risk_contribution_pct = (
            float(row.iloc[0]["risk_contribution_pct"]) if not row.empty and "risk_contribution_pct" in row.columns else projected_symbol_exposure_pct
        )
        missing_vol_ratio = float(row.iloc[0]["missing_vol_ratio"]) if not row.empty and "missing_vol_ratio" in row.columns else 1.0

        return self._risk_manager.evaluate(
            timestamp=datetime.now(UTC),
            symbol=route.symbol,
            current_equity=current_equity,
            equity_peak=equity_peak,
            symbol_exposure_pct=projected_symbol_exposure_pct,
            portfolio_exposure_pct=projected_portfolio_exposure_pct,
            concentration_score=concentration_score,
            correlated_exposure_pct=correlated_exposure_pct,
            vol_weighted_exposure_pct=vol_weighted_exposure_pct,
            risk_contribution_pct=risk_contribution_pct,
            missing_vol_ratio=missing_vol_ratio,
        )

    def _build_gateway(self, *, transport: object | None) -> OrderGateway:
        if transport is None:
            api_key, api_secret = _resolve_api_credentials("testnet-futures-live")
            transport = BinanceRestTransport(
                RestClientConfig(
                    base_url="https://testnet.binancefuture.com",
                    api_key=api_key,
                    api_secret=api_secret,
                    order_path="/fapi/v1/order",
                    time_path="/fapi/v1/time",
                    exchange_info_path="/fapi/v1/exchangeInfo",
                    sync_server_time=True,
                )
            )
        return OrderGateway(
            transport,  # type: ignore[arg-type]
            GatewayConfig(
                runtime_state_path=self.config.runtime_state_path,
                require_runtime_state=self._normalized_execution_mode() != "dry-run",
                allow_runtime_state_fail_open=bool(self._normalized_execution_mode() == "dry-run" and self.config.allow_runtime_state_fail_open),
                runtime_state_max_age_sec=int(self.config.runtime_state_max_age_sec),
                state_path=self.config.gateway_state_path,
                stale_signal_ttl_sec=self.config.stale_signal_ttl_sec,
            ),
        )

    def _configured_route_selection_path(self) -> str:
        path = str(self.config.route_selection_path).strip()
        if path:
            return path
        return str(self.config.weekly_revalidation_report_path).strip()

    def _configured_settings_path(self) -> str:
        path = str(self.config.settings_path).strip()
        if path:
            return path
        if self._normalized_execution_mode() == "production":
            return "config/config.prod.yaml"
        return ""

    def _load_effective_risk_config(self) -> EffectiveRiskConfig:
        settings_path = self._configured_settings_path()
        if settings_path:
            payload = yaml.safe_load(Path(settings_path).read_text(encoding="utf-8")) or {}
            risk = payload.get("risk", {}) if isinstance(payload, dict) else {}
            return EffectiveRiskConfig(
                source_path=settings_path,
                max_dd_pct=float(risk.get("max_drawdown_pct", 15.0)),
                max_symbol_exposure_pct=_coerce_float(
                    risk.get("max_symbol_exposure_pct", self.config.max_symbol_exposure_pct),
                    default=self.config.max_symbol_exposure_pct,
                ),
                max_portfolio_exposure_pct=_coerce_float(
                    risk.get("max_portfolio_exposure_pct", self.config.max_portfolio_exposure_pct),
                    default=self.config.max_portfolio_exposure_pct,
                ),
                max_correlated_exposure_pct=50.0,
                max_vol_weighted_exposure_pct=60.0,
                max_risk_contribution_pct=55.0,
            )
        return EffectiveRiskConfig(
            source_path="worker_cli_defaults",
            max_dd_pct=15.0,
            max_symbol_exposure_pct=float(self.config.max_symbol_exposure_pct),
            max_portfolio_exposure_pct=float(self.config.max_portfolio_exposure_pct),
            max_correlated_exposure_pct=50.0,
            max_vol_weighted_exposure_pct=60.0,
            max_risk_contribution_pct=55.0,
        )

    def _load_execution_config(self) -> ExecutionConfig:
        """Load execution configuration from settings."""
        settings_path = self._configured_settings_path()
        if settings_path:
            try:
                payload = yaml.safe_load(Path(settings_path).read_text(encoding="utf-8")) or {}
                execution = payload.get("execution", {}) if isinstance(payload, dict) else {}
                return ExecutionConfig(
                    enable_reconciliation=bool(execution.get("enable_reconciliation", False)),
                    reconciliation_state_path=str(execution.get("reconciliation_state_path", self.config.reconciliation_state_path)),
                )
            except Exception:
                logger.warning(f"Failed to load execution config from {settings_path}, using defaults")
        # Return default config if no settings file or load failed
        return ExecutionConfig(
            enable_reconciliation=self.config.enable_execution_reconciliation,
            reconciliation_state_path=self.config.reconciliation_state_path,
        )

    def _normalized_execution_mode(self) -> str:
        mode = str(self.config.execution_mode).strip().lower()
        if mode in {"prod", "production"}:
            return "production"
        if mode in {"dry-run", "dry_run", "dryrun"}:
            return "dry-run"
        return "testnet"

    def _route_selection_sync_enabled(self) -> bool:
        return bool(self.config.auto_sync_route_selection and self.config.auto_sync_weekly_symbols)

    def _refresh_symbols_from_route_selection(self) -> dict[str, object]:
        selection_path = self._configured_route_selection_path()
        snapshot: dict[str, object] = {
            "enabled": bool(self._route_selection_sync_enabled()),
            "status": "disabled" if not self._route_selection_sync_enabled() else "idle",
            "execution_mode": self._normalized_execution_mode(),
            "selection_path": selection_path,
            "report_path": selection_path,
            "trend_symbols": list(self._active_trend_symbols),
            "range_symbols": list(self._active_range_symbols),
            "trade_routes": [route.to_dict() for route in self._active_routes.values()],
            "symbols": list(self._active_symbols),
        }
        if not self._route_selection_sync_enabled():
            return snapshot

        report = read_json_with_recovery(selection_path)
        if not report:
            snapshot["status"] = "missing_or_invalid"
            return snapshot

        resolved = resolve_worker_routes(
            report,
            execution_mode=self._normalized_execution_mode(),
            default_timeframe=self.config.strategy_timeframe,
        )
        routes = None
        if resolved is not None:
            routes = tuple(
                TradeRoute(
                    symbol=route.symbol,
                    strategy=route.strategy,
                    timeframe=route.timeframe,
                    expected_regime=route.expected_regime,
                    candidate_status=route.candidate_status,
                    statistical_status=route.statistical_status,
                )
                for route in resolved
            )
        if routes is None:
            snapshot["status"] = "missing_or_invalid"
            return snapshot

        self._active_routes = {route.route_key(): route for route in routes}
        self._active_trend_symbols = tuple(route.symbol for route in routes if route.strategy == "trend")
        self._active_range_symbols = tuple(route.symbol for route in routes if route.strategy == "range")
        self._active_symbols = self._merge_symbols(self._base_symbols, self._active_trend_symbols, self._active_range_symbols)
        snapshot.update(
            {
                "status": "updated",
                "trend_symbols": list(self._active_trend_symbols),
                "range_symbols": list(self._active_range_symbols),
                "trade_routes": [route.to_dict() for route in self._active_routes.values()],
                "symbols": list(self._active_symbols),
            }
        )
        return snapshot

    def _routes_from_selection_payload(self, payload: dict[str, object]) -> tuple[TradeRoute, ...] | None:
        execution_mode = self._normalized_execution_mode()
        selection = payload.get("selection", {})
        if isinstance(selection, dict):
            trade_routes = self._normalize_trade_routes(selection.get("trade_routes"))
            if trade_routes is not None:
                if execution_mode != "production":
                    return trade_routes
                return tuple(route for route in trade_routes if route.statistical_status == "pass")

        statistical = payload.get("statistical_qualification", {})
        if not isinstance(statistical, dict) or str(statistical.get("status", "")) != "pass":
            return ()

        if isinstance(selection, dict):
            has_selection_keys = "trend_enabled_symbols" in selection or "range_enabled_symbols" in selection
            if has_selection_keys:
                timeframe = str(selection.get("timeframe", self.config.strategy_timeframe)).strip()
                trend_symbols = self._normalize_symbols(selection.get("trend_enabled_symbols"))
                range_symbols = self._normalize_symbols(selection.get("range_enabled_symbols"))
                routes = self._legacy_routes_from_symbols(
                    trend_symbols=trend_symbols,
                    range_symbols=range_symbols,
                    timeframe=timeframe or self.config.strategy_timeframe,
                )
                if routes is not None:
                    if execution_mode == "production":
                        return ()
                    return routes

        candidates = payload.get("candidates", {})
        if isinstance(candidates, dict):
            routes = self._routes_from_candidates(candidates)
            if routes is not None:
                return routes

        return None

    def _routes_from_candidates(self, payload: dict[str, object]) -> tuple[TradeRoute, ...] | None:
        routes: list[TradeRoute] = []
        for row in self._candidate_rows(payload):
            if str(row.get("candidate_status", "")) != "core":
                continue
            route = self._route_from_row(row)
            if route is None:
                continue
            routes.append(route)
        return tuple(routes) if routes else None

    def _candidate_rows(self, payload: dict[str, object]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        raw_rows = payload.get("rows", [])
        if isinstance(raw_rows, list):
            rows.extend(row for row in raw_rows if isinstance(row, dict))
        timeframe_reports = payload.get("timeframe_reports", [])
        if isinstance(timeframe_reports, list):
            for report in timeframe_reports:
                if not isinstance(report, dict):
                    continue
                nested_rows = report.get("rows", [])
                if isinstance(nested_rows, list):
                    rows.extend(row for row in nested_rows if isinstance(row, dict))
        return rows

    def _normalize_trade_routes(self, value: object) -> tuple[TradeRoute, ...] | None:
        if not isinstance(value, list):
            return None
        routes: list[TradeRoute] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            route = self._route_from_row(item)
            if route is None:
                continue
            routes.append(route)
        return tuple(routes) if routes else None

    def _legacy_routes_from_symbols(
        self,
        *,
        trend_symbols: tuple[str, ...] | None,
        range_symbols: tuple[str, ...] | None,
        timeframe: str,
    ) -> tuple[TradeRoute, ...] | None:
        routes: list[TradeRoute] = []
        for symbol in trend_symbols or ():
            routes.append(
                TradeRoute(
                    symbol=symbol,
                    strategy="trend",
                    timeframe=timeframe,
                    expected_regime="TREND",
                    candidate_status="legacy",
                    statistical_status="missing",
                )
            )
        for symbol in range_symbols or ():
            routes.append(
                TradeRoute(
                    symbol=symbol,
                    strategy="range",
                    timeframe=timeframe,
                    expected_regime="RANGE",
                    candidate_status="legacy",
                    statistical_status="missing",
                )
            )
        return tuple(routes) if routes else None

    def _route_from_row(
        self,
        row: dict[str, object],
        *,
        default_timeframe: str | None = None,
    ) -> TradeRoute | None:
        symbol = str(row.get("symbol", "")).strip()
        strategy = str(row.get("strategy", "")).strip()
        if not symbol or strategy not in {"trend", "range"}:
            return None
        timeframe = str(row.get("timeframe", "")).strip() or default_timeframe or self.config.strategy_timeframe
        expected_regime = str(row.get("expected_regime", "")).strip()
        if not expected_regime:
            expected_regime = "TREND" if strategy == "trend" else "RANGE"
        return TradeRoute(
            symbol=symbol,
            strategy=cast(Literal["trend", "range"], strategy),
            timeframe=timeframe,
            expected_regime=expected_regime,
            candidate_status=str(row.get("candidate_status", "core")),
            statistical_status=str(row.get("statistical_status", "missing")).strip() or "missing",
        )

    def _normalize_symbols(self, value: object) -> tuple[str, ...] | None:
        if value is None:
            return None
        return _csv_symbols(value)

    def _merge_symbols(self, *groups: tuple[str, ...]) -> tuple[str, ...]:
        merged: list[str] = []
        seen: set[str] = set()
        for group in groups:
            for symbol in group:
                if symbol and symbol not in seen:
                    seen.add(symbol)
                    merged.append(symbol)
        return tuple(merged)


def _csv_symbols(value: object) -> tuple[str, ...]:
    if isinstance(value, list | tuple):
        source = value
    elif isinstance(value, str):
        source = [item.strip() for item in value.split(",") if item.strip()]
    else:
        source = []
    seen: set[str] = set()
    ordered: list[str] = []
    for item in source:
        symbol = str(item).strip()
        if symbol and symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)
    return tuple(ordered)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            return float(value)
        return default
    except (TypeError, ValueError):
        return default


def _coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _read_line_cursor(path: Path) -> int:
    payload = read_json_with_recovery(path)
    return max(_coerce_int(payload.get("last_processed_line", 0)), 0)


def _write_line_cursor(path: Path, line_no: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_processed_line": max(int(line_no), 0),
        "updated_at": _now_iso(),
    }
    with FileLock(path.with_suffix(f"{path.suffix}.lock"), timeout_sec=1.0):
        path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _position_from_order_row(row: dict[str, object]) -> PositionState | None:
    if not bool(row.get("pre_position_exists", False)):
        return None
    qty = _coerce_float(row.get("pre_position_qty", 0.0) or 0.0)
    side = str(row.get("pre_position_side", "")).strip().lower()
    route_key = str(row.get("route_key", "")).strip()
    if qty <= 0.0 or side not in {"buy", "sell"} or not route_key:
        return None
    return PositionState(
        symbol=str(row.get("symbol", "")),
        strategy=str(row.get("strategy", "")).strip() or "legacy",
        timeframe=str(row.get("timeframe", "")).strip() or "15m",
        route_key=route_key,
        side=cast(Literal["buy", "sell"], side),
        qty=qty,
        avg_entry=_coerce_float(row.get("pre_position_avg_entry", 0.0) or 0.0),
        unrealized_pnl_pct=0.0,
        add_count=_coerce_int(row.get("pre_position_add_count", 0) or 0),
        updated_at=datetime.now(UTC),
    )


def _fill_price_from_order_row(row: dict[str, object]) -> float:
    order_type = str(row.get("order_type", "market")).strip().lower()
    limit_price = row.get("limit_price")
    if order_type == "limit" and isinstance(limit_price, int | float) and float(limit_price) > 0.0:
        return float(limit_price)
    return _coerce_float(row.get("price", 0.0) or 0.0)


def _fill_price_from_execution_event(
    event: ExecutionStreamEvent,
    order_row: dict[str, object],
) -> float:
    if float(event.avg_fill_price) > 0.0:
        return float(event.avg_fill_price)
    return _fill_price_from_order_row(order_row)


def _pandas_timeframe_rule(timeframe: str) -> str:
    rule_map = {
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
    }
    return rule_map.get(timeframe, timeframe)
