from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

import pandas as pd

Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 10_000.0
    fee_rate: float = 0.0004
    slippage_rate: float = 0.0005
    spread_rate: float = 0.0003
    execution_delay_bars: int = 1
    unit_size: float = 1.0


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

    trades: list[dict[str, object]] = []
    portfolio: list[dict[str, object]] = []

    cash = cfg.initial_cash
    position_qty = 0.0
    entry_price = 0.0
    equity_peak = cfg.initial_cash

    for i, row in enumerate(merged.itertuples(index=False), start=0):
        ts = _to_datetime_utc(row.timestamp)
        close = _to_float(row.close)
        high = _to_float(row.high)
        low = _to_float(row.low)

        delayed_idx = i + cfg.execution_delay_bars
        delayed_row = merged.iloc[delayed_idx] if delayed_idx < len(merged) else merged.iloc[i]
        exec_price_base = float(delayed_row["close"])

        blocked = (str(row.regime) == "HIGH_VOL") or (not bool(row.pass_filter))

        if bool(row.entry_signal) and not blocked and position_qty == 0.0:
            px = _apply_costed_price(exec_price_base, "buy", cfg)
            fee = px * cfg.unit_size * cfg.fee_rate
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
                )
            )

        if bool(row.exit_signal) and position_qty > 0.0:
            px = _apply_costed_price(exec_price_base, "sell", cfg)
            fee = px * position_qty * cfg.fee_rate
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
                )
            )
            position_qty = 0.0
            entry_price = 0.0

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
        return {"PF": 0.0, "Expectancy": 0.0, "WinRate": 0.0, "MaxDD": 0.0, "MonthlyPnL": 0.0}

    closed = _pair_roundtrips(trades_df)
    if closed.empty:
        win_rate = 0.0
        expectancy = 0.0
        pf = 0.0
    else:
        wins = closed[closed["pnl"] > 0.0]
        losses = closed[closed["pnl"] < 0.0]
        gross_profit = float(wins["pnl"].sum())
        gross_loss = float((-losses["pnl"]).sum())
        pf = gross_profit / gross_loss if gross_loss > 0 else 0.0
        win_rate = float((closed["pnl"] > 0.0).mean())
        expectancy = float(closed["pnl"].mean())

    max_dd = float(portfolio_df["drawdown"].max())
    final_equity = float(portfolio_df.iloc[-1]["equity"])
    monthly_pnl = final_equity - initial_cash
    return {
        "PF": pf,
        "Expectancy": expectancy,
        "WinRate": win_rate,
        "MaxDD": max_dd,
        "MonthlyPnL": monthly_pnl,
    }


_KEYS = ["symbol", "timeframe", "timestamp"]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in _KEYS:
        if col not in out.columns:
            raise ValueError(f"missing key column: {col}")
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out


def _apply_costed_price(price: float, side: Side, cfg: BacktestConfig) -> float:
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
    }


def _pair_roundtrips(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df.empty:
        return pd.DataFrame(columns=["entry_ts", "exit_ts", "pnl"])
    rows: list[dict[str, object]] = []
    open_trade: dict[str, object] | None = None
    for _, t in trades_df.iterrows():
        side = str(t["side"])
        if side == "buy" and open_trade is None:
            open_trade = dict(t)
            continue
        if side == "sell" and open_trade is not None:
            entry_value = _to_float(open_trade["price"]) * _to_float(
                open_trade["size"]
            ) + _to_float(open_trade["fee"])
            exit_value = _to_float(t["price"]) * _to_float(t["size"]) - _to_float(t["fee"])
            pnl = exit_value - entry_value
            rows.append(
                {
                    "entry_ts": open_trade["timestamp"],
                    "exit_ts": t["timestamp"],
                    "pnl": pnl,
                }
            )
            open_trade = None
    return pd.DataFrame(rows)


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
