from __future__ import annotations

import argparse
from datetime import UTC, datetime

from auto_trader.exchange.gateway import GatewayConfig, OrderGateway
from auto_trader.exchange.idempotency import build_client_order_id
from auto_trader.exchange.models import OrderRequest


class DummyTransport:
    def send_order(self, order: OrderRequest) -> tuple[bool, str, str]:
        return True, f"ord_{order.client_order_id[-6:]}", "accepted"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Dry-run exchange order gateway.")
    p.add_argument("--symbol", required=True)
    p.add_argument("--side", choices=["buy", "sell"], required=True)
    p.add_argument("--qty", type=float, required=True)
    p.add_argument("--strategy", default="range")
    p.add_argument("--regime", default="RANGE")
    p.add_argument("--pass-filter", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    ts = datetime.now(UTC)
    cid = build_client_order_id(
        symbol=args.symbol,
        side=args.side,
        signal_ts=ts,
        strategy=args.strategy,
    )
    req = OrderRequest(
        symbol=args.symbol,
        side=args.side,
        qty=args.qty,
        signal_ts=ts,
        regime=args.regime,
        pass_filter=bool(args.pass_filter),
        client_order_id=cid,
    )
    gw = OrderGateway(DummyTransport(), GatewayConfig())
    event = gw.submit(req)
    print(f"status={event.status} reason={event.reason} order_id={event.order_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
