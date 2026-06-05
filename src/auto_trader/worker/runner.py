from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from auto_trader.exchange.cli import _resolve_api_credentials
from auto_trader.exchange.gateway import GatewayConfig, OrderGateway
from auto_trader.exchange.idempotency import build_client_order_id
from auto_trader.exchange.models import OrderRequest
from auto_trader.exchange.rest_client import BinanceRestTransport, RestClientConfig
from auto_trader.features.engine import FeatureConfig, compute_features
from auto_trader.position.manager import PositionConfig, PositionManager
from auto_trader.position.models import FillEvent, PositionState
from auto_trader.position.store import PositionStore
from auto_trader.regime.classifier import RegimeConfig, classify_regime
from auto_trader.stateio import FileLock, read_json_with_recovery
from auto_trader.strategy.ml_filter import apply_signal_ml_filter
from auto_trader.strategy.range_strategy import RangeStrategyConfig, generate_range_signals
from auto_trader.strategy.session_gate import apply_session_gate
from auto_trader.strategy.trend_strategy import TrendStrategyConfig, generate_trend_signals
from auto_trader.worker.market_data import (
    BinanceKlineClient,
    BinanceKlineClientConfig,
    resample_ohlcv,
)
from auto_trader.worker.state import WorkerState

OrderMode = Literal["market", "limit"]


@dataclass(frozen=True)
class WorkerConfig:
    symbols: tuple[str, ...]
    trend_symbols: tuple[str, ...]
    range_symbols: tuple[str, ...]
    trend_order_mode: OrderMode = "limit"
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
    gateway_state_path: str = "data/exchange/gateway_state.json"
    positions_dir: str = "data/positions"
    worker_state_path: str = "data/runtime/worker_state.json"
    order_events_path: str = "data/exchange/order_events.jsonl"
    ml_artifact_path: str | None = None
    max_iterations: int | None = None
    max_symbol_exposure_pct: float = 25.0
    max_portfolio_exposure_pct: float = 70.0
    range_strategy: RangeStrategyConfig = RangeStrategyConfig()
    trend_strategy: TrendStrategyConfig = TrendStrategyConfig()
    feature_config: FeatureConfig = FeatureConfig()
    regime_config: RegimeConfig = RegimeConfig()
    position_config: PositionConfig = PositionConfig()


class LiveTradingWorker:
    def __init__(
        self,
        *,
        config: WorkerConfig,
        market_client: BinanceKlineClient | None = None,
        transport: object | None = None,
        sleeper=time.sleep,
    ) -> None:
        self.config = config
        self.market_client = market_client or BinanceKlineClient(
            BinanceKlineClientConfig(
                base_url=config.market_base_url,
                klines_path=config.market_klines_path,
            )
        )
        self.sleeper = sleeper
        self.position_store = PositionStore(config.positions_dir)
        self.position_manager = PositionManager(config.position_config)
        self.position_manager.replace_positions(self.position_store.load())
        self.worker_state = self._load_worker_state()
        self.gateway = self._build_gateway(transport=transport)

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
        cycle_started_at = _now_iso()
        summary: dict[str, object] = {
            "cycle_started_at": cycle_started_at,
            "orders": [],
            "symbols": {},
            "runtime": runtime_state,
        }
        mark_prices: dict[str, float] = {}
        try:
            closed_by_symbol = self._load_closed_market_frames()
            mark_prices = {
                symbol: float(frame["close"].iloc[-1])
                for symbol, frame in closed_by_symbol.items()
                if not frame.empty
            }
        except Exception as exc:
            self.worker_state.last_error = f"market_data_error:{exc.__class__.__name__}"
            self.worker_state.last_cycle_at = cycle_started_at
            self.worker_state.updated_at = _now_iso()
            self.worker_state.save(self.config.worker_state_path)
            return summary

        if runtime_state["emergency_stop"] or runtime_state["close_all_requested"]:
            flattened = self._flatten_positions(mark_prices, reason="emergency_close")
            summary["orders"] = flattened
            self._persist_cycle(summary, cycle_started_at)
            return summary

        if not runtime_state["trading_enabled"]:
            self._persist_cycle(summary, cycle_started_at)
            return summary

        for symbol in self.config.symbols:
            symbol_summary: dict[str, object] = {"status": "skipped"}
            frame_15m = closed_by_symbol.get(symbol)
            if frame_15m is None or frame_15m.empty:
                symbol_summary["status"] = "missing_data"
                summary["symbols"][symbol] = symbol_summary
                continue
            latest_bar_ts = str(pd.to_datetime(frame_15m["timestamp"].iloc[-1], utc=True))
            mark_price = float(frame_15m["close"].iloc[-1])
            mark_prices[symbol] = mark_price
            route = self._route_for_symbol(symbol)
            if route is None:
                symbol_summary["status"] = "not_enabled"
                summary["symbols"][symbol] = symbol_summary
                continue

            state_key = f"{route}:{symbol}"
            already_processed = (
                self.worker_state.last_processed_bars.get(state_key) == latest_bar_ts
            )
            signal_frame = self._build_signal_frame(symbol=symbol, frame_15m=frame_15m, route=route)
            if signal_frame is None or signal_frame.empty:
                self.worker_state.last_processed_bars[state_key] = latest_bar_ts
                symbol_summary["status"] = "no_signal"
                summary["symbols"][symbol] = symbol_summary
                continue

            latest = signal_frame.iloc[-1].to_dict()
            symbol_summary["signal"] = {
                "timestamp": str(latest.get("timestamp", "")),
                "regime": str(latest.get("regime", "")),
                "entry_signal": bool(latest.get("entry_signal", False)),
                "exit_signal": bool(latest.get("exit_signal", False)),
                "add_signal": bool(latest.get("add_signal", False)),
                "pass_filter": bool(latest.get("pass_filter", False)),
                "reason_codes": latest.get("signal_reason_codes", []),
            }

            pos = self.position_manager.get(symbol)
            risk_blocked = self.position_manager.risk_blocked(
                mark_prices=mark_prices,
                equity=self.config.equity,
                symbol=symbol,
            )
            symbol_summary["risk_blocked"] = risk_blocked
            self.worker_state.last_processed_bars[state_key] = latest_bar_ts
            if already_processed:
                symbol_summary["status"] = "already_processed"
                symbol_summary["trade"] = {
                    "order_submitted": False,
                    "status": "already_processed",
                }
            else:
                action_result = self._maybe_trade(
                    symbol=symbol,
                    route=route,
                    latest_row=latest,
                    position=pos,
                    mark_price=mark_price,
                    risk_blocked=risk_blocked,
                    allow_runtime_gate=False,
                )
                symbol_summary["trade"] = action_result
                if action_result.get("order_submitted"):
                    summary["orders"].append(action_result)
            summary["symbols"][symbol] = symbol_summary

        self._persist_cycle(summary, cycle_started_at)
        return summary

    def _persist_cycle(self, summary: dict[str, object], cycle_started_at: str) -> None:
        self.worker_state.last_cycle_at = cycle_started_at
        self.worker_state.last_results = dict(summary.get("symbols", {}))
        self.worker_state.last_error = ""
        self.worker_state.updated_at = _now_iso()
        self.worker_state.save(self.config.worker_state_path)
        self.position_store.save(self.position_manager.all_positions())

    def _flatten_positions(
        self, mark_prices: dict[str, float], *, reason: str
    ) -> list[dict[str, object]]:
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
                strategy="emergency",
                allow_runtime_gate=True,
                action="emergency_close",
                price=price,
                is_add=False,
            )
            submitted["reason"] = reason
            orders.append(submitted)
        return orders

    def _maybe_trade(
        self,
        *,
        symbol: str,
        route: Literal["trend", "range"],
        latest_row: dict[str, object],
        position: PositionState | None,
        mark_price: float,
        risk_blocked: bool,
        allow_runtime_gate: bool,
    ) -> dict[str, object]:
        signal_ts = pd.to_datetime(latest_row.get("timestamp"), utc=True).to_pydatetime()
        regime = str(latest_row.get("regime", ""))
        pass_filter = bool(latest_row.get("pass_filter", False))
        entry_signal = bool(latest_row.get("entry_signal", False))
        exit_signal = bool(latest_row.get("exit_signal", False))
        add_signal = bool(latest_row.get("add_signal", False))
        size_ratio = float(latest_row.get("position_size_ratio", 0.0))
        reason_codes = latest_row.get("signal_reason_codes", [])
        order_mode = (
            self.config.trend_order_mode if route == "trend" else self.config.range_order_mode
        )
        if route == "trend" and symbol not in self.config.trend_symbols:
            return {"order_submitted": False, "status": "disabled"}
        if route == "range" and symbol not in self.config.range_symbols:
            return {"order_submitted": False, "status": "disabled"}

        if position is not None and exit_signal:
            qty = float(position.qty)
            if qty <= 0:
                return {"order_submitted": False, "status": "no_position"}
            return self._submit_order(
                symbol=symbol,
                side="sell" if position.side == "buy" else "buy",
                qty=qty,
                order_type=order_mode,
                limit_price=self._limit_price(
                    order_mode, mark_price, "sell" if position.side == "buy" else "buy"
                ),
                signal_ts=signal_ts,
                regime=regime,
                pass_filter=pass_filter,
                strategy=route,
                allow_runtime_gate=allow_runtime_gate,
                action="exit",
                price=mark_price,
                is_add=False,
                reason_codes=reason_codes,
            )

        if risk_blocked:
            return {"order_submitted": False, "status": "risk_blocked"}

        if position is None and entry_signal and pass_filter:
            qty = self._entry_qty(mark_price, size_ratio)
            if qty <= 0:
                return {"order_submitted": False, "status": "qty_zero"}
            return self._submit_order(
                symbol=symbol,
                side="buy",
                qty=qty,
                order_type=order_mode,
                limit_price=self._limit_price(order_mode, mark_price, "buy"),
                signal_ts=signal_ts,
                regime=regime,
                pass_filter=pass_filter,
                strategy=route,
                allow_runtime_gate=allow_runtime_gate,
                action="entry",
                price=mark_price,
                is_add=False,
                reason_codes=reason_codes,
            )

        if position is not None and add_signal and pass_filter:
            qty = self._entry_qty(mark_price, size_ratio)
            if qty <= 0:
                return {"order_submitted": False, "status": "qty_zero"}
            return self._submit_order(
                symbol=symbol,
                side="buy",
                qty=qty,
                order_type=order_mode,
                limit_price=self._limit_price(order_mode, mark_price, "buy"),
                signal_ts=signal_ts,
                regime=regime,
                pass_filter=pass_filter,
                strategy=route,
                allow_runtime_gate=allow_runtime_gate,
                action="add",
                price=mark_price,
                is_add=True,
                reason_codes=reason_codes,
            )

        return {"order_submitted": False, "status": "no_action"}

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
        allow_runtime_gate: bool,
        action: str,
        price: float,
        is_add: bool,
        reason_codes: object | None = None,
    ) -> dict[str, object]:
        cid = build_client_order_id(
            symbol=symbol,
            side=side,
            signal_ts=signal_ts,
            strategy=strategy,
        )
        req = OrderRequest(
            symbol=symbol,
            side=side,
            qty=float(qty),
            signal_ts=signal_ts,
            regime=regime,
            pass_filter=bool(pass_filter),
            client_order_id=cid,
            order_type=order_type,
            limit_price=limit_price,
        )
        event = self.gateway.submit(
            req,
            allow_runtime_gate=allow_runtime_gate,
            allow_policy_gate=allow_runtime_gate,
        )
        log_row = {
            "ts": _now_iso(),
            "symbol": symbol,
            "strategy": strategy,
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
            "limit_price": event.limit_price,
            "price": float(price),
            "signal_ts": signal_ts.isoformat(),
            "regime": regime,
            "reason_codes": reason_codes if reason_codes is not None else [],
        }
        self._append_order_event(log_row)

        result = dict(log_row)
        result["order_submitted"] = True
        result["gateway_status"] = event.status
        result["gateway_reason"] = event.reason
        if event.status == "ack":
            fill = FillEvent(
                symbol=symbol,
                side=side,
                qty=float(qty),
                price=float(
                    event.limit_price
                    if event.order_type == "limit" and event.limit_price
                    else price
                ),
                filled_at=event.ack_at or datetime.now(UTC),
                is_add=is_add,
            )
            state = self.position_manager.apply_fill(fill)
            self.position_store.save(self.position_manager.all_positions())
            result["position_qty"] = state.qty
            result["position_avg_entry"] = state.avg_entry
            result["position_side"] = state.side
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

    def _route_for_symbol(self, symbol: str) -> Literal["trend", "range"] | None:
        if symbol in self.config.trend_symbols:
            return "trend"
        if symbol in self.config.range_symbols:
            return "range"
        return None

    def _build_signal_frame(
        self, *, symbol: str, frame_15m: pd.DataFrame, route: Literal["trend", "range"]
    ) -> pd.DataFrame | None:
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if frame_15m.empty or not required.issubset(frame_15m.columns):
            return None
        base = frame_15m.copy().reset_index(drop=True)
        base["symbol"] = symbol
        base["timeframe"] = self.config.strategy_timeframe
        features = compute_features(base, config=self.config.feature_config)
        regime = classify_regime(features, config=self.config.regime_config)
        if route == "range":
            signals = generate_range_signals(
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

        if self.config.ml_artifact_path:
            try:
                signals = apply_signal_ml_filter(
                    features_df=features,
                    regime_df=regime,
                    signals_df=signals,
                    artifact_path=self.config.ml_artifact_path,
                )
            except Exception as exc:
                self.worker_state.last_error = f"ml_filter_error:{exc.__class__.__name__}"
                return None
        closed_cutoff = pd.to_datetime(base["timestamp"].iloc[-1], utc=True).floor(
            _pandas_timeframe_rule(self.config.strategy_timeframe)
        )
        out = signals[pd.to_datetime(signals["timestamp"], utc=True) <= closed_cutoff].copy()
        return out

    def _load_closed_market_frames(self) -> dict[str, pd.DataFrame]:
        closed_frames: dict[str, pd.DataFrame] = {}
        for symbol in self.config.symbols:
            raw = self.market_client.fetch_klines(
                symbol,
                interval=self.config.market_interval,
                limit=self.config.market_limit,
            )
            if raw.empty:
                continue
            raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
            raw = raw.sort_values("timestamp")
            cutoff = pd.to_datetime(raw["timestamp"].iloc[-1], utc=True).floor(
                _pandas_timeframe_rule(self.config.strategy_timeframe)
            )
            resampled = resample_ohlcv(raw, self.config.strategy_timeframe)
            resampled["timestamp"] = pd.to_datetime(resampled["timestamp"], utc=True)
            closed = resampled[resampled["timestamp"] <= cutoff].copy().reset_index(drop=True)
            if not closed.empty:
                closed["symbol"] = symbol
                closed["timeframe"] = self.config.strategy_timeframe
            closed_frames[symbol] = closed
        return closed_frames

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
            return WorkerState()

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
                    sync_server_time=True,
                )
            )
        return OrderGateway(
            transport,  # type: ignore[arg-type]
            GatewayConfig(
                runtime_state_path=self.config.runtime_state_path,
                state_path=self.config.gateway_state_path,
                stale_signal_ttl_sec=self.config.stale_signal_ttl_sec,
            ),
        )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _pandas_timeframe_rule(timeframe: str) -> str:
    rule_map = {
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
    }
    return rule_map.get(timeframe, timeframe)
