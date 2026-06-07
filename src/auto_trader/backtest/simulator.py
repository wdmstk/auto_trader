from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

import numpy as np
import pandas as pd

Side = Literal["buy", "sell"]
OrderMode = Literal["market", "limit"]


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 10_000.0
    fee_rate: float = 0.0004
    slippage_rate: float = 0.0005
    spread_rate: float = 0.0003
    execution_delay_bars: int = 1
    unit_size: float = 1.0
    order_mode: OrderMode = "market"
    maker_fee_rate: float = 0.0
    taker_fee_rate: float = 0.0
    limit_offset_rate: float = 0.0
    limit_partial_fill_ratio: float = 0.1
    limit_book_depth_units: float = 0.0
    limit_queue_ahead_units: float = 0.0
    limit_volume_participation_rate: float = 0.0


def run_backtest(
    *,
    ohlcv_df: pd.DataFrame,
    signals_df: pd.DataFrame,
    ml_df: pd.DataFrame | None = None,
    config: BacktestConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    cfg = config or BacktestConfig()
    market = _normalize(ohlcv_df)
    sig = _normalize(signals_df)
    if ml_df is not None:
        ml = _normalize(ml_df)
        sig = sig.merge(
            ml[["symbol", "timeframe", "timestamp", "pass_filter"]],
            on=_KEYS,
            how="left",
        )
    if "pass_filter" not in sig.columns:
        sig["pass_filter"] = True
    sig["pass_filter"] = sig["pass_filter"].fillna(False).astype(bool)

    merged = market.merge(sig, on=_KEYS, how="left")
    merged = merged.sort_values(_KEYS).reset_index(drop=True)
    merged["entry_signal"] = merged["entry_signal"].fillna(False).astype(bool)
    merged["exit_signal"] = merged["exit_signal"].fillna(False).astype(bool)
    merged["regime"] = merged["regime"].fillna("")
    merged["pass_filter"] = merged["pass_filter"].fillna(False).astype(bool)

    n_rows = len(merged)
    timestamp_values = merged["timestamp"].to_numpy(copy=False)
    close_values = merged["close"].astype(float).to_numpy(copy=False)
    high_values = merged["high"].astype(float).to_numpy(copy=False)
    low_values = merged["low"].astype(float).to_numpy(copy=False)
    volume_values = (
        merged.get("volume", pd.Series(0.0, index=merged.index))
        .fillna(0.0)
        .astype(float)
        .to_numpy(copy=False)
    )
    entry_values = merged["entry_signal"].to_numpy(dtype=bool, copy=False)
    exit_values = merged["exit_signal"].to_numpy(dtype=bool, copy=False)
    pass_values = merged["pass_filter"].to_numpy(dtype=bool, copy=False)
    regime_values = merged["regime"].astype(str).to_numpy(copy=False)

    if n_rows > 0:
        exec_idx = np.arange(n_rows, dtype=int) + int(cfg.execution_delay_bars)
        np.clip(exec_idx, 0, n_rows - 1, out=exec_idx)
        delayed_close_values = close_values[exec_idx]
        delayed_high_values = high_values[exec_idx]
        delayed_low_values = low_values[exec_idx]
        delayed_volume_values = volume_values[exec_idx]
        delayed_next_high_values = np.empty(n_rows, dtype=float)
        delayed_next_low_values = np.empty(n_rows, dtype=float)
        delayed_next_high_values[:-1] = high_values[1:]
        delayed_next_low_values[:-1] = low_values[1:]
        delayed_next_high_values[-1] = np.nan
        delayed_next_low_values[-1] = np.nan
        delayed_next_high_values = delayed_next_high_values[exec_idx]
        delayed_next_low_values = delayed_next_low_values[exec_idx]
    else:
        delayed_close_values = close_values
        delayed_high_values = high_values
        delayed_low_values = low_values
        delayed_volume_values = volume_values
        delayed_next_high_values = np.array([], dtype=float)
        delayed_next_low_values = np.array([], dtype=float)

    blocked_values = (regime_values == "HIGH_VOL") | (~pass_values)
    market_buy_prices = delayed_close_values * (1.0 + cfg.slippage_rate + cfg.spread_rate)
    market_sell_prices = delayed_close_values * (1.0 - cfg.slippage_rate - cfg.spread_rate)
    limit_buy_prices = delayed_close_values * (1.0 - cfg.limit_offset_rate)
    limit_sell_prices = delayed_close_values * (1.0 + cfg.limit_offset_rate)

    trades: list[dict[str, object]] = []
    portfolio: list[dict[str, object]] = []

    cash = cfg.initial_cash
    position_qty = 0.0
    entry_price = 0.0
    equity_peak = cfg.initial_cash

    for i in range(n_rows):
        ts = timestamp_values[i].to_pydatetime()
        close = float(close_values[i])
        high = float(high_values[i])
        low = float(low_values[i])

        blocked = bool(blocked_values[i])

        if entry_values[i] and not blocked and position_qty == 0.0:
            if cfg.order_mode == "market":
                px = float(market_buy_prices[i])
                fee = px * cfg.unit_size * _taker_fee_rate(cfg)
                cash -= (px * cfg.unit_size) + fee
                position_qty = cfg.unit_size
                entry_price = px
                trades.append(
                    _trade_row(
                        ts=ts,
                        side="buy",
                        price=px,
                        size=cfg.unit_size,
                        fee=fee,
                        slippage=cfg.slippage_rate,
                        spread=cfg.spread_rate,
                        status="filled",
                        order_mode=cfg.order_mode,
                    )
                )
            else:
                limit_px = float(limit_buy_prices[i])
                next_high = delayed_next_high_values[i]
                next_low = delayed_next_low_values[i]
                touched, dwell = _limit_fill_state(
                    side="buy",
                    limit_price=limit_px,
                    cur_high=float(delayed_high_values[i]),
                    cur_low=float(delayed_low_values[i]),
                    next_high=None if np.isnan(next_high) else float(next_high),
                    next_low=None if np.isnan(next_low) else float(next_low),
                )
                if dwell:
                    fee = limit_px * cfg.unit_size * _maker_fee_rate(cfg)
                    cash -= (limit_px * cfg.unit_size) + fee
                    position_qty = cfg.unit_size
                    entry_price = limit_px
                    trades.append(
                        _trade_row(
                            ts=ts,
                            side="buy",
                            price=limit_px,
                            size=cfg.unit_size,
                            fee=fee,
                            slippage=0.0,
                            spread=0.0,
                            status="filled",
                            order_mode=cfg.order_mode,
                        )
                    )
                elif touched:
                    partial_qty = _limit_partial_qty(
                        order_qty=cfg.unit_size,
                        cfg=cfg,
                        bar_volume=float(delayed_volume_values[i]),
                    )
                    if partial_qty > 0:
                        fee = limit_px * partial_qty * _maker_fee_rate(cfg)
                        cash -= (limit_px * partial_qty) + fee
                        position_qty = partial_qty
                        entry_price = limit_px
                        trades.append(
                            _trade_row(
                                ts=ts,
                                side="buy",
                                price=limit_px,
                                size=partial_qty,
                                fee=fee,
                                slippage=0.0,
                                spread=0.0,
                                status="partial",
                                order_mode=cfg.order_mode,
                            )
                        )
                    rem = max(0.0, cfg.unit_size - partial_qty)
                    if rem > 0:
                        trades.append(
                            _trade_row(
                                ts=ts,
                                side="buy",
                                price=limit_px,
                                size=rem,
                                fee=0.0,
                                slippage=0.0,
                                spread=0.0,
                                status="canceled",
                                order_mode=cfg.order_mode,
                            )
                        )
                else:
                    trades.append(
                        _trade_row(
                            ts=ts,
                            side="buy",
                            price=limit_px,
                            size=cfg.unit_size,
                            fee=0.0,
                            slippage=0.0,
                            spread=0.0,
                            status="expired",
                            order_mode=cfg.order_mode,
                        )
                    )

        if exit_values[i] and position_qty > 0.0:
            if cfg.order_mode == "market":
                px = float(market_sell_prices[i])
                fee = px * position_qty * _taker_fee_rate(cfg)
                cash += (px * position_qty) - fee
                trades.append(
                    _trade_row(
                        ts=ts,
                        side="sell",
                        price=px,
                        size=position_qty,
                        fee=fee,
                        slippage=cfg.slippage_rate,
                        spread=cfg.spread_rate,
                        status="filled",
                        order_mode=cfg.order_mode,
                    )
                )
                position_qty = 0.0
                entry_price = 0.0
            else:
                limit_px = float(limit_sell_prices[i])
                next_high = delayed_next_high_values[i]
                next_low = delayed_next_low_values[i]
                touched, dwell = _limit_fill_state(
                    side="sell",
                    limit_price=limit_px,
                    cur_high=float(delayed_high_values[i]),
                    cur_low=float(delayed_low_values[i]),
                    next_high=None if np.isnan(next_high) else float(next_high),
                    next_low=None if np.isnan(next_low) else float(next_low),
                )
                if dwell:
                    fee = limit_px * position_qty * _maker_fee_rate(cfg)
                    cash += (limit_px * position_qty) - fee
                    trades.append(
                        _trade_row(
                            ts=ts,
                            side="sell",
                            price=limit_px,
                            size=position_qty,
                            fee=fee,
                            slippage=0.0,
                            spread=0.0,
                            status="filled",
                            order_mode=cfg.order_mode,
                        )
                    )
                    position_qty = 0.0
                    entry_price = 0.0
                elif touched:
                    partial_qty = _limit_partial_qty(
                        order_qty=position_qty,
                        cfg=cfg,
                        bar_volume=float(delayed_volume_values[i]),
                    )
                    if partial_qty > 0:
                        fee = limit_px * partial_qty * _maker_fee_rate(cfg)
                        cash += (limit_px * partial_qty) - fee
                        trades.append(
                            _trade_row(
                                ts=ts,
                                side="sell",
                                price=limit_px,
                                size=partial_qty,
                                fee=fee,
                                slippage=0.0,
                                spread=0.0,
                                status="partial",
                                order_mode=cfg.order_mode,
                            )
                        )
                        position_qty -= partial_qty
                    if position_qty > 0:
                        trades.append(
                            _trade_row(
                                ts=ts,
                                side="sell",
                                price=limit_px,
                                size=position_qty,
                                fee=0.0,
                                slippage=0.0,
                                spread=0.0,
                                status="canceled",
                                order_mode=cfg.order_mode,
                            )
                        )
                else:
                    trades.append(
                        _trade_row(
                            ts=ts,
                            side="sell",
                            price=limit_px,
                            size=position_qty,
                            fee=0.0,
                            slippage=0.0,
                            spread=0.0,
                            status="expired",
                            order_mode=cfg.order_mode,
                        )
                    )

        position_value = position_qty * close
        equity = cash + position_value
        equity_peak = max(equity_peak, equity)
        drawdown = 0.0 if equity_peak == 0 else (equity_peak - equity) / equity_peak
        portfolio.append(
            {
                "timestamp": ts.replace(tzinfo=UTC),
                "equity": equity,
                "cash": cash,
                "position_value": position_value,
                "drawdown": drawdown,
                "high": high,
                "low": low,
                "entry_price": entry_price,
            }
        )

    trades_df = pd.DataFrame(trades)
    portfolio_df = pd.DataFrame(portfolio)
    metrics = summarize_metrics(trades_df, portfolio_df, cfg.initial_cash)
    return trades_df, portfolio_df, metrics


def summarize_metrics(
    trades_df: pd.DataFrame,
    portfolio_df: pd.DataFrame,
    initial_cash: float,
) -> dict[str, float]:
    if portfolio_df.empty:
        return {
            "PF": 0.0,
            "Expectancy": 0.0,
            "ExpectancyBps": 0.0,
            "WinRate": 0.0,
            "MaxDD": 0.0,
            "MonthlyPnL": 0.0,
            "PeriodPnL": 0.0,
            "GrossPnLEst": 0.0,
            "TotalCostEst": 0.0,
            "FeeCost": 0.0,
            "ImpactCostEst": 0.0,
            "ClosedTrades": 0.0,
            "LimitOrderCount": 0.0,
            "LimitFilledCount": 0.0,
            "LimitPartialCount": 0.0,
            "LimitExpiredCount": 0.0,
            "LimitCanceledCount": 0.0,
            "LimitFillRate": 0.0,
            "LimitMakerFillRate": 0.0,
            "LimitTakerLikeRate": 0.0,
        }

    closed = _pair_roundtrips(trades_df)
    if closed.empty:
        win_rate = 0.0
        expectancy = 0.0
        expectancy_bps = 0.0
        pf = 0.0
    else:
        wins = closed[closed["pnl"] > 0.0]
        losses = closed[closed["pnl"] < 0.0]
        gross_profit = float(wins["pnl"].sum())
        gross_loss = float((-losses["pnl"]).sum())
        # No-loss samples should still surface as a very strong PF candidate.
        # We keep a finite sentinel instead of infinity so downstream scoring and JSON
        # serialization remain stable.
        pf = gross_profit / gross_loss if gross_loss > 0 else (100.0 if gross_profit > 0 else 0.0)
        win_rate = float((closed["pnl"] > 0.0).mean())
        expectancy = float(closed["pnl"].mean())
        valid_notional = closed[closed["entry_notional"] > 0.0]
        if valid_notional.empty:
            expectancy_bps = 0.0
        else:
            expectancy_bps = float(
                (valid_notional["pnl"] / valid_notional["entry_notional"]).mean() * 10_000.0
            )

    max_dd = float(portfolio_df["drawdown"].max())
    final_equity = float(portfolio_df.iloc[-1]["equity"])
    period_pnl = final_equity - initial_cash
    fee_cost = (
        float(trades_df.get("fee", pd.Series(dtype=float)).fillna(0.0).sum())
        if not trades_df.empty
        else 0.0
    )
    limit_stats = _limit_order_stats(trades_df)
    if trades_df.empty:
        impact_cost = 0.0
    else:
        px = trades_df["price"].fillna(0.0).astype(float).abs()
        sz = trades_df["size"].fillna(0.0).astype(float).abs()
        slip = (
            trades_df.get("slippage", pd.Series(0.0, index=trades_df.index))
            .fillna(0.0)
            .astype(float)
            .abs()
        )
        sprd = (
            trades_df.get("spread", pd.Series(0.0, index=trades_df.index))
            .fillna(0.0)
            .astype(float)
            .abs()
        )
        impact_cost = float((px * sz * (slip + sprd)).sum())
    total_cost = fee_cost + impact_cost
    gross_pnl_est = period_pnl + total_cost
    return {
        "PF": pf,
        "Expectancy": expectancy,
        "ExpectancyBps": expectancy_bps,
        "WinRate": win_rate,
        "MaxDD": max_dd,
        "MonthlyPnL": period_pnl,
        "PeriodPnL": period_pnl,
        "GrossPnLEst": gross_pnl_est,
        "TotalCostEst": total_cost,
        "FeeCost": fee_cost,
        "ImpactCostEst": impact_cost,
        "ClosedTrades": float(len(closed)),
        **limit_stats,
    }


_KEYS = ["symbol", "timeframe", "timestamp"]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in _KEYS:
        if col not in out.columns:
            raise ValueError(f"missing key column: {col}")
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out


def _apply_market_price(price: float, side: Side, cfg: BacktestConfig) -> float:
    direction = 1.0 if side == "buy" else -1.0
    slip = price * cfg.slippage_rate * direction
    spread = price * cfg.spread_rate * direction
    return price + slip + spread


def _trade_row(
    *,
    ts: datetime,
    side: Side,
    price: float,
    size: float,
    fee: float,
    slippage: float,
    spread: float,
    status: str,
    order_mode: str,
) -> dict[str, object]:
    return {
        "timestamp": ts.replace(tzinfo=UTC),
        "side": side,
        "price": price,
        "size": size,
        "fee": fee,
        "slippage": slippage,
        "spread": spread,
        "status": status,
        "order_mode": order_mode,
    }


def _limit_fill_state(
    *,
    side: Side,
    limit_price: float,
    cur_high: float,
    cur_low: float,
    next_high: float | None,
    next_low: float | None,
) -> tuple[bool, bool]:
    touched = cur_low <= limit_price <= cur_high
    if not touched:
        return False, False
    if next_high is None or next_low is None:
        return True, False
    dwell = next_low <= limit_price <= next_high
    return True, dwell


def _limit_partial_qty(*, order_qty: float, cfg: BacktestConfig, bar_volume: float) -> float:
    baseline = max(0.0, min(order_qty, order_qty * cfg.limit_partial_fill_ratio))
    if (
        cfg.limit_book_depth_units <= 0.0
        and cfg.limit_queue_ahead_units <= 0.0
        and cfg.limit_volume_participation_rate <= 0.0
    ):
        return baseline

    depth_cap = cfg.limit_book_depth_units
    if cfg.limit_volume_participation_rate > 0.0 and bar_volume > 0.0:
        volume_cap = bar_volume * cfg.limit_volume_participation_rate
        depth_cap = min(depth_cap, volume_cap) if depth_cap > 0.0 else volume_cap
    if depth_cap <= 0.0:
        return 0.0
    executable = max(0.0, depth_cap - max(0.0, cfg.limit_queue_ahead_units))
    return max(0.0, min(order_qty, executable))


def _maker_fee_rate(cfg: BacktestConfig) -> float:
    return cfg.maker_fee_rate if cfg.maker_fee_rate > 0.0 else cfg.fee_rate


def _taker_fee_rate(cfg: BacktestConfig) -> float:
    return cfg.taker_fee_rate if cfg.taker_fee_rate > 0.0 else cfg.fee_rate


def _pair_roundtrips(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return pd.DataFrame(columns=["entry_ts", "exit_ts", "pnl", "entry_notional"])
    rows: list[dict[str, object]] = []
    open_trade: dict[str, object] | None = None
    for t in trades_df.itertuples(index=False):
        side = str(t.side)
        if side == "buy" and open_trade is None:
            open_trade = {
                "timestamp": t.timestamp,
                "price": t.price,
                "size": t.size,
                "fee": t.fee,
            }
            continue
        if side == "sell" and open_trade is not None:
            entry_value = _to_float(open_trade["price"]) * _to_float(
                open_trade["size"]
            ) + _to_float(open_trade["fee"])
            exit_value = _to_float(t.price) * _to_float(t.size) - _to_float(t.fee)
            pnl = exit_value - entry_value
            rows.append(
                {
                    "entry_ts": open_trade["timestamp"],
                    "exit_ts": t.timestamp,
                    "pnl": pnl,
                    "entry_notional": _to_float(open_trade["price"])
                    * _to_float(open_trade["size"]),
                }
            )
            open_trade = None
    return pd.DataFrame(rows)


def _limit_order_stats(trades_df: pd.DataFrame) -> dict[str, float]:
    if (
        trades_df.empty
        or "order_mode" not in trades_df.columns
        or "status" not in trades_df.columns
    ):
        return {
            "LimitOrderCount": 0.0,
            "LimitFilledCount": 0.0,
            "LimitPartialCount": 0.0,
            "LimitExpiredCount": 0.0,
            "LimitCanceledCount": 0.0,
            "LimitFillRate": 0.0,
            "LimitMakerFillRate": 0.0,
            "LimitTakerLikeRate": 0.0,
        }

    limit_trades = trades_df[trades_df["order_mode"].astype(str) == "limit"]
    if limit_trades.empty:
        return {
            "LimitOrderCount": 0.0,
            "LimitFilledCount": 0.0,
            "LimitPartialCount": 0.0,
            "LimitExpiredCount": 0.0,
            "LimitCanceledCount": 0.0,
            "LimitFillRate": 0.0,
            "LimitMakerFillRate": 0.0,
            "LimitTakerLikeRate": 0.0,
        }

    filled = float((limit_trades["status"] == "filled").sum())
    partial = float((limit_trades["status"] == "partial").sum())
    expired = float((limit_trades["status"] == "expired").sum())
    canceled = float((limit_trades["status"] == "canceled").sum())
    total = float(len(limit_trades))
    maker_fill_rate = filled / total if total > 0 else 0.0
    fill_rate = (filled + partial) / total if total > 0 else 0.0
    taker_like_rate = 1.0 - maker_fill_rate if total > 0 else 0.0
    return {
        "LimitOrderCount": total,
        "LimitFilledCount": filled,
        "LimitPartialCount": partial,
        "LimitExpiredCount": expired,
        "LimitCanceledCount": canceled,
        "LimitFillRate": fill_rate,
        "LimitMakerFillRate": maker_fill_rate,
        "LimitTakerLikeRate": taker_like_rate,
    }


def _to_float(v: object) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _to_datetime_utc(v: object) -> datetime:
    ts = pd.Timestamp(cast(Any, v))
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    dt = ts.to_pydatetime()
    if not isinstance(dt, datetime):
        raise TypeError("timestamp conversion failed")
    return dt
