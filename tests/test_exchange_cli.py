from __future__ import annotations

from pytest import MonkeyPatch

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
