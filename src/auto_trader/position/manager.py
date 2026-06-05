from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from auto_trader.position.models import FillEvent, PositionState, now_utc


@dataclass(frozen=True)
class PositionConfig:
    max_add_count: int = 2
    max_symbol_exposure_pct: float = 25.0
    max_portfolio_exposure_pct: float = 70.0


class PositionManager:
    def __init__(self, config: PositionConfig | None = None) -> None:
        self.config = config or PositionConfig()
        self._positions: dict[str, PositionState] = {}
        self._emergency_stopped = False

    def apply_fill(self, fill: FillEvent) -> PositionState:
        if self._emergency_stopped:
            raise RuntimeError("position manager is emergency stopped")
        if _invalid_fill(fill):
            self._emergency_stopped = True
            raise ValueError("invalid fill detected; emergency stop engaged")
        pos = self._positions.get(fill.symbol)
        if pos is None:
            created = PositionState(
                symbol=fill.symbol,
                side=fill.side,
                qty=fill.qty,
                avg_entry=fill.price,
                unrealized_pnl_pct=0.0,
                add_count=1 if fill.is_add else 0,
                updated_at=fill.filled_at,
            )
            self._positions[fill.symbol] = created
            return created

        updated = self._update_existing_position(pos, fill)
        self._positions[fill.symbol] = updated
        return updated

    def update_mark_price(
        self,
        symbol: str,
        mark_price: float,
        ts: datetime | None = None,
    ) -> PositionState | None:
        pos = self._positions.get(symbol)
        if pos is None or pos.qty <= 0.0:
            return pos
        pnl = _calc_unrealized_pnl_pct(pos.side, pos.avg_entry, mark_price)
        updated = PositionState(
            symbol=pos.symbol,
            side=pos.side,
            qty=pos.qty,
            avg_entry=pos.avg_entry,
            unrealized_pnl_pct=pnl,
            add_count=pos.add_count,
            updated_at=ts or now_utc(),
        )
        self._positions[symbol] = updated
        return updated

    def get(self, symbol: str) -> PositionState | None:
        return self._positions.get(symbol)

    def all_positions(self) -> list[PositionState]:
        return list(self._positions.values())

    def replace_positions(self, positions: list[PositionState]) -> None:
        self._positions = {pos.symbol: pos for pos in positions}

    def emergency_stopped(self) -> bool:
        return self._emergency_stopped

    def clear_emergency_stop(self) -> None:
        self._emergency_stopped = False

    def exposure_snapshot(
        self,
        *,
        mark_prices: dict[str, float],
        equity: float,
    ) -> dict[str, float]:
        if equity <= 0:
            raise ValueError("equity must be positive")
        symbol_exposure: dict[str, float] = {}
        total_notional = 0.0
        for symbol, pos in self._positions.items():
            price = mark_prices.get(symbol, pos.avg_entry)
            notional = abs(pos.qty * price)
            symbol_exposure[f"{symbol}_exposure_pct"] = (notional / equity) * 100.0
            total_notional += notional
        symbol_exposure["portfolio_exposure_pct"] = (total_notional / equity) * 100.0
        return symbol_exposure

    def risk_blocked(self, *, mark_prices: dict[str, float], equity: float, symbol: str) -> bool:
        snap = self.exposure_snapshot(mark_prices=mark_prices, equity=equity)
        symbol_exp = snap.get(f"{symbol}_exposure_pct", 0.0)
        portfolio_exp = snap.get("portfolio_exposure_pct", 0.0)
        return (
            symbol_exp > self.config.max_symbol_exposure_pct
            or portfolio_exp > self.config.max_portfolio_exposure_pct
        )

    def _update_existing_position(self, pos: PositionState, fill: FillEvent) -> PositionState:
        # same direction -> weighted average update
        if _same_direction(pos.side, fill.side):
            new_qty = pos.qty + fill.qty
            if new_qty <= 0:
                new_qty = 0.0
            avg = (
                ((pos.avg_entry * pos.qty) + (fill.price * fill.qty)) / new_qty
                if new_qty > 0
                else 0.0
            )
            can_inc_add = fill.is_add and pos.add_count < self.config.max_add_count
            new_add = pos.add_count + 1 if can_inc_add else pos.add_count
            return PositionState(
                symbol=pos.symbol,
                side=pos.side,
                qty=new_qty,
                avg_entry=avg,
                unrealized_pnl_pct=pos.unrealized_pnl_pct,
                add_count=new_add,
                updated_at=fill.filled_at,
            )

        # opposite direction -> reduce/close; no side flip in this phase
        new_qty = max(0.0, pos.qty - fill.qty)
        new_add = pos.add_count if new_qty > 0 else 0
        return PositionState(
            symbol=pos.symbol,
            side=pos.side,
            qty=new_qty,
            avg_entry=pos.avg_entry if new_qty > 0 else 0.0,
            unrealized_pnl_pct=0.0 if new_qty == 0 else pos.unrealized_pnl_pct,
            add_count=new_add,
            updated_at=fill.filled_at,
        )


def _same_direction(pos_side: str, fill_side: str) -> bool:
    return (pos_side == "buy" and fill_side == "buy") or (
        pos_side == "sell" and fill_side == "sell"
    )


def _calc_unrealized_pnl_pct(side: str, avg_entry: float, mark_price: float) -> float:
    if avg_entry <= 0:
        return 0.0
    if side == "buy":
        return (mark_price - avg_entry) / avg_entry
    return (avg_entry - mark_price) / avg_entry


def _invalid_fill(fill: FillEvent) -> bool:
    if not fill.symbol:
        return True
    if fill.side not in {"buy", "sell"}:
        return True
    if fill.qty <= 0.0:
        return True
    if fill.price <= 0.0:
        return True
    return False
