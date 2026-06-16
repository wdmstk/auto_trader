from __future__ import annotations

import sys

from pytest import CaptureFixture, MonkeyPatch

import auto_trader.exchange.cli as exchange_cli

RESOLVE_CREDENTIALS = exchange_cli._resolve_api_credentials


def test_resolve_api_credentials_prefers_testnet_vars(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "tn_key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "tn_secret")
    monkeypatch.setenv("BINANCE_API_KEY", "prod_key")
    monkeypatch.setenv("BINANCE_API_SECRET", "prod_secret")

    key, secret = RESOLVE_CREDENTIALS("testnet-live")
    assert key == "tn_key"
    assert secret == "tn_secret"


def test_resolve_api_credentials_falls_back_to_default_vars(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("BINANCE_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_TESTNET_API_SECRET", raising=False)
    monkeypatch.setenv("BINANCE_API_KEY", "prod_key")
    monkeypatch.setenv("BINANCE_API_SECRET", "prod_secret")

    key, secret = RESOLVE_CREDENTIALS("testnet-live")
    assert key == ""
    assert secret == ""


def test_resolve_api_credentials_for_futures_testnet(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_API_KEY", "fut_key")
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_API_SECRET", "fut_secret")
    key, secret = RESOLVE_CREDENTIALS("testnet-futures-live")
    assert key == "fut_key"
    assert secret == "fut_secret"


def test_build_parser_accepts_order_type_and_limit_price() -> None:
    parser = exchange_cli.build_parser()
    args = parser.parse_args(
        [
            "--symbol",
            "BTCUSDT",
            "--side",
            "buy",
            "--qty",
            "0.1",
            "--order-type",
            "limit",
            "--limit-price",
            "65000",
        ]
    )
    assert args.order_type == "limit"
    assert args.limit_price == 65000.0
    assert args.runtime_state_max_age_sec == 120
    assert args.allow_runtime_state_fail_open is False


def test_main_rejects_limit_without_limit_price(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "exchange",
            "--symbol",
            "BTCUSDT",
            "--side",
            "buy",
            "--qty",
            "0.1",
            "--order-type",
            "limit",
        ],
    )
    code = exchange_cli.main()
    captured = capsys.readouterr()
    assert code == 1
    assert "invalid_args:limit_price_required_for_limit" in captured.out
