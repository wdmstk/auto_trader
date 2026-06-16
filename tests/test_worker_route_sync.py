from __future__ import annotations

from auto_trader.worker.route_sync import resolve_worker_routes


def test_resolve_worker_routes_keeps_fail_routes_in_testnet() -> None:
    payload = {
        "selection": {
            "trade_routes": [
                {
                    "symbol": "BNBUSDT",
                    "strategy": "range",
                    "timeframe": "30m",
                    "expected_regime": "RANGE",
                    "candidate_status": "core",
                    "statistical_status": "fail",
                }
            ]
        }
    }

    routes = resolve_worker_routes(
        payload,
        execution_mode="testnet",
        default_timeframe="15m",
    )

    assert routes is not None
    assert len(routes) == 1
    assert routes[0].statistical_status == "fail"


def test_resolve_worker_routes_drops_fail_routes_in_production() -> None:
    payload = {
        "selection": {
            "trade_routes": [
                {
                    "symbol": "BNBUSDT",
                    "strategy": "range",
                    "timeframe": "30m",
                    "expected_regime": "RANGE",
                    "candidate_status": "core",
                    "statistical_status": "fail",
                }
            ]
        }
    }

    routes = resolve_worker_routes(
        payload,
        execution_mode="production",
        default_timeframe="15m",
    )

    assert routes == ()
