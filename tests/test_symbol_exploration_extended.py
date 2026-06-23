from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from auto_trader.analysis.symbol_exploration import (
    _as_float,
    _eligible_usdt_symbols,
    _is_ascii_alnum_token,
    _normalize_symbols,
    _symbol_meta_map,
    load_existing_symbols,
    write_symbol_exploration_artifacts,
)


def test_eligible_usdt_symbols_filters_correctly() -> None:
    exchange_info: dict[str, Any] = {
        "symbols": [
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "status": "TRADING", "quoteAsset": "USDT"},
            {"symbol": "ETHBTC", "baseAsset": "ETH", "status": "TRADING", "quoteAsset": "BTC"},
            {"symbol": "BADUSDT", "baseAsset": "BAD", "status": "BREAK", "quoteAsset": "USDT"},
            {"symbol": "DOGEUSDT", "baseAsset": "DOGE", "status": "TRADING", "quoteAsset": "USDT"},
        ]
    }
    result = _eligible_usdt_symbols(exchange_info)
    assert result == ["BTCUSDT", "DOGEUSDT"]


def test_eligible_usdt_symbols_handles_non_list_symbols() -> None:
    assert _eligible_usdt_symbols({"symbols": "not_a_list"}) == []


def test_eligible_usdt_symbols_skips_non_dict_items() -> None:
    exchange_info: dict[str, Any] = {"symbols": ["not_a_dict", 42]}
    assert _eligible_usdt_symbols(exchange_info) == []


def test_eligible_usdt_symbols_skips_empty_symbol() -> None:
    exchange_info: dict[str, Any] = {
        "symbols": [{"symbol": "", "status": "TRADING", "quoteAsset": "USDT"}]
    }
    assert _eligible_usdt_symbols(exchange_info) == []


def test_eligible_usdt_symbols_deduplicates() -> None:
    exchange_info: dict[str, Any] = {
        "symbols": [
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "status": "TRADING", "quoteAsset": "USDT"},
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "status": "TRADING", "quoteAsset": "USDT"},
        ]
    }
    assert _eligible_usdt_symbols(exchange_info) == ["BTCUSDT"]


def test_eligible_usdt_symbols_skips_non_ascii() -> None:
    exchange_info: dict[str, Any] = {
        "symbols": [
            {"symbol": "币安USDT", "baseAsset": "币安", "status": "TRADING", "quoteAsset": "USDT"},
        ]
    }
    assert _eligible_usdt_symbols(exchange_info) == []


def test_eligible_usdt_symbols_skips_spot_disallowed() -> None:
    exchange_info: dict[str, Any] = {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "baseAsset": "BTC",
                "status": "TRADING",
                "quoteAsset": "USDT",
                "isSpotTradingAllowed": False,
            },
        ]
    }
    assert _eligible_usdt_symbols(exchange_info) == []


def test_symbol_meta_map_builds_map() -> None:
    exchange_info: dict[str, Any] = {
        "symbols": [
            {"symbol": "BTCUSDT", "baseAsset": "BTC"},
            {"symbol": "ETHUSDT", "baseAsset": "ETH"},
        ]
    }
    meta = _symbol_meta_map(exchange_info)
    assert "BTCUSDT" in meta
    assert meta["BTCUSDT"]["baseAsset"] == "BTC"


def test_symbol_meta_map_handles_non_list() -> None:
    assert _symbol_meta_map({"symbols": "bad"}) == {}


def test_symbol_meta_map_skips_non_dict_and_empty() -> None:
    exchange_info: dict[str, Any] = {"symbols": [42, {"symbol": ""}]}
    assert _symbol_meta_map(exchange_info) == {}


def test_normalize_symbols_deduplicates_and_uppercases() -> None:
    result = _normalize_symbols(["btcusdt", "ETHUSDT", "btcusdt"])
    assert result == ["BTCUSDT", "ETHUSDT"]


def test_normalize_symbols_strips_whitespace() -> None:
    result = _normalize_symbols([" btc ", " ETH"])
    assert result == ["BTC", "ETH"]


def test_normalize_symbols_skips_empty() -> None:
    result = _normalize_symbols(["", " "])
    assert result == []


def test_as_float_valid() -> None:
    assert _as_float("3.14") == 3.14
    assert _as_float(42) == 42.0


def test_as_float_invalid() -> None:
    assert _as_float("abc") == 0.0
    assert _as_float(None) == 0.0


def test_is_ascii_alnum_token_valid() -> None:
    assert _is_ascii_alnum_token("BTC") is True
    assert _is_ascii_alnum_token("123abc") is True


def test_is_ascii_alnum_token_invalid() -> None:
    assert _is_ascii_alnum_token("") is False
    assert _is_ascii_alnum_token("币安") is False
    assert _is_ascii_alnum_token("BTC-USD") is False


def test_load_existing_symbols_no_parquet_dir(tmp_path: Path) -> None:
    assert load_existing_symbols(tmp_path) == []


def test_load_existing_symbols_skips_no_underscore(tmp_path: Path) -> None:
    import pandas as pd

    parquet_dir = tmp_path / "parquet"
    parquet_dir.mkdir()
    pd.DataFrame([{"x": 1}]).to_parquet(parquet_dir / "NOUNDERSCORE.parquet")
    assert load_existing_symbols(tmp_path) == []


def test_write_symbol_exploration_artifacts_json_only(tmp_path: Path) -> None:
    report: dict[str, Any] = {
        "selected_symbols": ["BTCUSDT"],
        "selected_count": 1,
    }
    json_path = tmp_path / "out.json"
    write_symbol_exploration_artifacts(report, json_path=json_path)
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["selected_count"] == 1


def test_write_symbol_exploration_artifacts_with_env(tmp_path: Path) -> None:
    report: dict[str, Any] = {
        "selected_symbols": ["BTCUSDT", "ETHUSDT"],
        "selected_count": 2,
    }
    json_path = tmp_path / "out.json"
    env_path = tmp_path / "out.env"
    write_symbol_exploration_artifacts(report, json_path=json_path, env_path=env_path)
    assert env_path.exists()
    env_content = env_path.read_text(encoding="utf-8")
    assert "SYMBOLS=BTCUSDT,ETHUSDT" in env_content
    assert "SYMBOL_EXPLORATION_SELECTED_COUNT=2" in env_content
