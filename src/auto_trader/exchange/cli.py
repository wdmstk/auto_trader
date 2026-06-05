from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime
from typing import Protocol

from auto_trader.exchange.gateway import GatewayConfig, OrderGateway
from auto_trader.exchange.idempotency import build_client_order_id
from auto_trader.exchange.models import OrderRequest
from auto_trader.exchange.rest_client import BinanceRestTransport, RestClientConfig


class DummyTransport:
    def send_order(self, order: OrderRequest) -> tuple[bool, str, str]:
        return True, f"ord_{order.client_order_id[-6:]}", "accepted"


class _OrderTransport(Protocol):
    def send_order(self, order: OrderRequest) -> tuple[bool, str, str]: ...


def _resolve_api_credentials(mode: str) -> tuple[str, str]:
    if mode == "testnet-live":
        key = os.getenv("BINANCE_TESTNET_API_KEY", "")
        secret = os.getenv("BINANCE_TESTNET_API_SECRET", "")
        return key, secret
    if mode == "testnet-futures-live":
        key = os.getenv("BINANCE_FUTURES_TESTNET_API_KEY", "")
        secret = os.getenv("BINANCE_FUTURES_TESTNET_API_SECRET", "")
        return key, secret
    return os.getenv("BINANCE_API_KEY", ""), os.getenv("BINANCE_API_SECRET", "")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Exchange order gateway CLI.")
    p.add_argument("--symbol", required=True)
    p.add_argument("--side", choices=["buy", "sell"], required=True)
    p.add_argument("--qty", type=float, required=True)
    p.add_argument("--order-type", choices=["market", "limit"], default="market")
    p.add_argument("--limit-price", type=float, default=None)
    p.add_argument("--strategy", default="range")
    p.add_argument("--regime", default="RANGE")
    p.add_argument("--pass-filter", action="store_true")
    p.add_argument(
        "--mode",
        choices=["dry-run", "testnet-live", "testnet-futures-live"],
        default="dry-run",
    )
    p.add_argument("--runtime-state-path", default=None)
    p.add_argument("--state-path", default=None)
    p.add_argument("--base-url", default="https://testnet.binance.vision")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.order_type == "limit" and args.limit_price is None:
        print("status=rejected reason=invalid_args:limit_price_required_for_limit order_id=")
        return 1
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
        order_type=args.order_type,
        limit_price=args.limit_price,
    )
    transport: _OrderTransport
    if args.mode == "dry-run":
        transport = DummyTransport()
    else:
        api_key, api_secret = _resolve_api_credentials(args.mode)
        base_url = args.base_url
        if (
            args.mode == "testnet-futures-live"
            and args.base_url == "https://testnet.binance.vision"
        ):
            base_url = "https://testnet.binancefuture.com"
        order_path = "/api/v3/order"
        if args.mode == "testnet-futures-live":
            order_path = "/fapi/v1/order"
        transport = BinanceRestTransport(
            RestClientConfig(
                base_url=base_url,
                api_key=api_key,
                api_secret=api_secret,
                order_path=order_path,
                time_path=(
                    "/fapi/v1/time" if args.mode == "testnet-futures-live" else "/api/v3/time"
                ),
                sync_server_time=True,
            )
        )
    gw = OrderGateway(
        transport,
        GatewayConfig(
            runtime_state_path=args.runtime_state_path,
            state_path=args.state_path,
        ),
    )
    event = gw.submit(req)
    print(f"status={event.status} reason={event.reason} order_id={event.order_id}")
    return 0 if event.status == "ack" else 1


if __name__ == "__main__":
    raise SystemExit(main())
