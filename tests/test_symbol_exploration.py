from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from auto_trader.analysis.symbol_exploration import (
    load_existing_symbols,
    rank_usdt_symbols,
    resolve_symbol_exploration,
)


class _FakeBinanceClient:
    def __init__(
        self,
        exchange_info: dict[str, Any],
        tickers: list[dict[str, Any]],
        base_url: str = "https://test",
    ) -> None:
        self._exchange_info = exchange_info
        self._tickers = tickers
        self.base_url = base_url

    def fetch_exchange_info(self) -> dict[str, Any]:
        return self._exchange_info

    def fetch_24h_tickers(self) -> list[dict[str, Any]]:
        return self._tickers


def test_load_existing_symbols_reads_existing_parquet_names(tmp_path: Path) -> None:
    parquet_dir = tmp_path / "parquet"
    parquet_dir.mkdir(parents=True)
    pd.DataFrame([{"symbol": "ETHUSDT", "value": 1}]).to_parquet(parquet_dir / "ETHUSDT_1m.parquet")
    pd.DataFrame([{"symbol": "DOGEUSDT", "value": 1}]).to_parquet(
        parquet_dir / "DOGEUSDT_15m.parquet"
    )

    assert load_existing_symbols(tmp_path) == ["DOGEUSDT", "ETHUSDT"]


def test_rank_usdt_symbols_filters_existing_and_sorts_by_volume() -> None:
    exchange_info = {
        "symbols": [
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "status": "TRADING", "quoteAsset": "USDT"},
            {"symbol": "ETHUSDT", "baseAsset": "ETH", "status": "TRADING", "quoteAsset": "USDT"},
            {"symbol": "DOGEUSDT", "baseAsset": "DOGE", "status": "TRADING", "quoteAsset": "USDT"},
            {"symbol": "XRPUSDT", "baseAsset": "XRP", "status": "TRADING", "quoteAsset": "USDT"},
            {
                "symbol": "FDUSDUSDT",
                "baseAsset": "FDUSD",
                "status": "TRADING",
                "quoteAsset": "USDT",
            },
            {"symbol": "PAXGUSDT", "baseAsset": "PAXG", "status": "TRADING", "quoteAsset": "USDT"},
            {
                "symbol": "币安人生USDT",
                "baseAsset": "币安人生",
                "status": "TRADING",
                "quoteAsset": "USDT",
            },
            {"symbol": "BADUSDT", "baseAsset": "BAD", "status": "BREAK", "quoteAsset": "USDT"},
            {"symbol": "BNBBTC", "baseAsset": "BNB", "status": "TRADING", "quoteAsset": "BTC"},
        ]
    }
    tickers = [
        {"symbol": "BTCUSDT", "quoteVolume": "300.0", "priceChangePercent": "1.0"},
        {"symbol": "ETHUSDT", "quoteVolume": "500.0", "priceChangePercent": "2.0"},
        {"symbol": "DOGEUSDT", "quoteVolume": "200.0", "priceChangePercent": "3.0"},
        {"symbol": "XRPUSDT", "quoteVolume": "400.0", "priceChangePercent": "4.0"},
        {"symbol": "PAXGUSDT", "quoteVolume": "999.0", "priceChangePercent": "0.1"},
    ]

    ranked = rank_usdt_symbols(
        exchange_info,
        tickers,
        excluded_symbols=["BTCUSDT", "ETHUSDT"],
        limit=2,
    )

    assert [row["symbol"] for row in ranked] == ["XRPUSDT", "DOGEUSDT"]
    assert [row["quote_volume"] for row in ranked] == [400.0, 200.0]


def test_resolve_symbol_exploration_builds_env_ready_selection(tmp_path: Path) -> None:
    parquet_dir = tmp_path / "parquet"
    parquet_dir.mkdir(parents=True)
    pd.DataFrame([{"symbol": "ETHUSDT", "value": 1}]).to_parquet(parquet_dir / "ETHUSDT_1m.parquet")

    client = _FakeBinanceClient(
        {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "baseAsset": "BTC",
                    "status": "TRADING",
                    "quoteAsset": "USDT",
                },
                {
                    "symbol": "ETHUSDT",
                    "baseAsset": "ETH",
                    "status": "TRADING",
                    "quoteAsset": "USDT",
                },
                {
                    "symbol": "DOGEUSDT",
                    "baseAsset": "DOGE",
                    "status": "TRADING",
                    "quoteAsset": "USDT",
                },
                {
                    "symbol": "XRPUSDT",
                    "baseAsset": "XRP",
                    "status": "TRADING",
                    "quoteAsset": "USDT",
                },
                {
                    "symbol": "FDUSDUSDT",
                    "baseAsset": "FDUSD",
                    "status": "TRADING",
                    "quoteAsset": "USDT",
                },
                {
                    "symbol": "PAXGUSDT",
                    "baseAsset": "PAXG",
                    "status": "TRADING",
                    "quoteAsset": "USDT",
                },
                {
                    "symbol": "币安人生USDT",
                    "baseAsset": "币安人生",
                    "status": "TRADING",
                    "quoteAsset": "USDT",
                },
            ]
        },
        [
            {"symbol": "BTCUSDT", "quoteVolume": "100.0"},
            {"symbol": "ETHUSDT", "quoteVolume": "500.0"},
            {"symbol": "DOGEUSDT", "quoteVolume": "700.0"},
            {"symbol": "XRPUSDT", "quoteVolume": "600.0"},
            {"symbol": "FDUSDUSDT", "quoteVolume": "1000.0"},
            {"symbol": "PAXGUSDT", "quoteVolume": "2000.0"},
            {"symbol": "币安人生USDT", "quoteVolume": "3000.0"},
        ],
    )

    report = resolve_symbol_exploration(
        client=client,
        data_root=tmp_path,
        limit=2,
        excluded_symbols=["BTCUSDT"],
    )

    assert report["existing_symbols"] == ["ETHUSDT"]
    assert report["excluded_symbols"] == ["ETHUSDT", "BTCUSDT"]
    assert report["selected_symbols"] == ["DOGEUSDT", "XRPUSDT"]
    assert report["selected_count"] == 2
    assert report["status"] == "pass"


def test_rank_usdt_symbols_excludes_stablecoin_like_base_assets() -> None:
    exchange_info = {
        "symbols": [
            {"symbol": "ETHUSDT", "baseAsset": "ETH", "status": "TRADING", "quoteAsset": "USDT"},
            {
                "symbol": "FDUSDUSDT",
                "baseAsset": "FDUSD",
                "status": "TRADING",
                "quoteAsset": "USDT",
            },
            {"symbol": "EURUSDT", "baseAsset": "EUR", "status": "TRADING", "quoteAsset": "USDT"},
            {"symbol": "UUSDT", "baseAsset": "U", "status": "TRADING", "quoteAsset": "USDT"},
        ]
    }
    tickers = [
        {"symbol": "ETHUSDT", "quoteVolume": "500.0"},
        {"symbol": "FDUSDUSDT", "quoteVolume": "1000.0"},
        {"symbol": "EURUSDT", "quoteVolume": "900.0"},
        {"symbol": "UUSDT", "quoteVolume": "800.0"},
        {"symbol": "PAXGUSDT", "quoteVolume": "700.0"},
        {"symbol": "币安人生USDT", "quoteVolume": "600.0"},
    ]

    ranked = rank_usdt_symbols(exchange_info, tickers, limit=10)
    assert [row["symbol"] for row in ranked] == ["ETHUSDT"]


def test_rank_usdt_symbols_applies_min_quote_volume() -> None:
    exchange_info = {
        "symbols": [
            {"symbol": "AAAUSDT", "baseAsset": "AAA", "status": "TRADING", "quoteAsset": "USDT"},
            {"symbol": "BBBUSDT", "baseAsset": "BBB", "status": "TRADING", "quoteAsset": "USDT"},
            {"symbol": "CCCUSDT", "baseAsset": "CCC", "status": "TRADING", "quoteAsset": "USDT"},
        ]
    }
    tickers = [
        {"symbol": "AAAUSDT", "quoteVolume": "10000000.0"},
        {"symbol": "BBBUSDT", "quoteVolume": "30000000.0"},
        {"symbol": "CCCUSDT", "quoteVolume": "50000000.0"},
    ]

    ranked = rank_usdt_symbols(exchange_info, tickers, min_quote_volume=30000000.0, limit=10)
    assert [row["symbol"] for row in ranked] == ["CCCUSDT", "BBBUSDT"]
