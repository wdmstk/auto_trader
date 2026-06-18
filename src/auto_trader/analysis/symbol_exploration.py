from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from auto_trader.data.binance_client import BinanceKlineClient
from auto_trader.utils import write_json_file

DEFAULT_EXCLUDED_BASE_ASSETS: frozenset[str] = frozenset(
    {
        "BUSD",
        "DAI",
        "EUR",
        "FDUSD",
        "PAXG",
        "RLUSD",
        "TUSD",
        "USDE",
        "USD1",
        "USDC",
        "USDP",
        "USDT",
        "UST",
        "USTC",
        "PAX",
        "EURI",
        "AEUR",
        "XAUT",
        "U",
    }
)


@dataclass(frozen=True)
class SymbolExplorationConfig:
    base_url: str = "https://api.binance.com"
    data_root: Path = Path("data")
    limit: int = 20
    min_quote_volume: float = 0.0
    excluded_symbols: tuple[str, ...] = ()


class SymbolExplorationClient(Protocol):
    base_url: str

    def fetch_exchange_info(self) -> dict[str, Any]: ...

    def fetch_24h_tickers(self) -> list[dict[str, Any]]: ...


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve new Binance USDT symbols for exploratory revalidation.")
    parser.add_argument("--base-url", default="https://api.binance.com")
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--min-quote-volume", type=float, default=0.0)
    parser.add_argument("--exclude-symbols", default="")
    parser.add_argument("--exclude-base-assets", default="")
    parser.add_argument("--json-path", required=True)
    parser.add_argument("--env-path", default="")
    return parser


def resolve_symbol_exploration(
    *,
    client: SymbolExplorationClient,
    data_root: str | Path = "data",
    limit: int = 20,
    min_quote_volume: float = 0.0,
    excluded_symbols: Iterable[str] = (),
    excluded_base_assets: Iterable[str] = (),
) -> dict[str, Any]:
    existing_symbols = load_existing_symbols(data_root)
    excluded = _normalize_symbols([*existing_symbols, *excluded_symbols])
    excluded_bases = _normalize_symbols([*DEFAULT_EXCLUDED_BASE_ASSETS, *excluded_base_assets])

    exchange_info = client.fetch_exchange_info()
    tickers = client.fetch_24h_tickers()
    eligible_symbols = _eligible_usdt_symbols(exchange_info)
    ranked_all = rank_usdt_symbols(
        exchange_info,
        tickers,
        excluded_symbols=excluded,
        excluded_base_assets=excluded_bases,
        limit=0,
        min_quote_volume=min_quote_volume,
    )
    selected_rows = ranked_all[:limit] if limit > 0 else ranked_all
    selected_symbols = [row["symbol"] for row in selected_rows]
    return {
        "base_url": client.base_url,
        "data_root": str(Path(data_root)),
        "limit": int(limit),
        "min_quote_volume": float(min_quote_volume),
        "existing_symbols": existing_symbols,
        "excluded_symbols": excluded,
        "excluded_base_assets": excluded_bases,
        "universe_size": len(eligible_symbols),
        "eligible_symbols": eligible_symbols,
        "ranked_symbols": ranked_all,
        "selected_symbols": selected_symbols,
        "selected_count": len(selected_symbols),
        "status": "pass" if selected_symbols else "warn",
    }


def rank_usdt_symbols(
    exchange_info: dict[str, Any],
    tickers: list[dict[str, Any]],
    *,
    excluded_symbols: Iterable[str] = (),
    excluded_base_assets: Iterable[str] = (),
    limit: int = 20,
    min_quote_volume: float = 0.0,
) -> list[dict[str, Any]]:
    excluded = set(_normalize_symbols(excluded_symbols))
    excluded_bases = set(_normalize_symbols([*DEFAULT_EXCLUDED_BASE_ASSETS, *excluded_base_assets]))
    eligible = _eligible_usdt_symbols(exchange_info)
    symbol_meta = _symbol_meta_map(exchange_info)
    ticker_map = {str(row.get("symbol", "")).strip(): row for row in tickers}

    rows: list[dict[str, Any]] = []
    for symbol in eligible:
        if symbol in excluded:
            continue
        meta = symbol_meta.get(symbol, {})
        base_asset = str(meta.get("baseAsset", "")).strip().upper()
        if not _is_ascii_alnum_token(base_asset):
            continue
        if base_asset in excluded_bases:
            continue
        ticker = ticker_map.get(symbol, {})
        quote_volume = _as_float(ticker.get("quoteVolume", 0.0))
        if quote_volume < min_quote_volume:
            continue
        rows.append(
            {
                "symbol": symbol,
                "base_asset": base_asset,
                "quote_volume": quote_volume,
                "price_change_percent": _as_float(ticker.get("priceChangePercent", 0.0)),
                "last_price": _as_float(ticker.get("lastPrice", 0.0)),
                "volume": _as_float(ticker.get("volume", 0.0)),
            }
        )

    rows.sort(key=lambda row: (-row["quote_volume"], row["symbol"]))
    if limit > 0:
        rows = rows[:limit]
    return rows


def load_existing_symbols(data_root: str | Path) -> list[str]:
    root = Path(data_root)
    parquet_dir = root / "parquet"
    if not parquet_dir.exists():
        return []

    symbols: list[str] = []
    seen: set[str] = set()
    for path in sorted(parquet_dir.glob("*.parquet")):
        stem = path.stem
        if "_" not in stem:
            continue
        symbol = stem.rsplit("_", 1)[0].strip()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def write_symbol_exploration_artifacts(
    report: dict[str, Any],
    *,
    json_path: str | Path,
    env_path: str | Path | None = None,
) -> None:
    write_json_file(json_path, report)

    if env_path is None:
        return

    env_out = Path(env_path)
    env_out.parent.mkdir(parents=True, exist_ok=True)
    env_out.write_text(
        "\n".join(
            [
                f"SYMBOLS={','.join(report.get('selected_symbols', []))}",
                f"SYMBOL_EXPLORATION_SELECTED_COUNT={report.get('selected_count', 0)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = build_parser().parse_args()
    client = BinanceKlineClient(base_url=args.base_url)
    excluded_symbols = [item.strip() for item in str(args.exclude_symbols).split(",") if item.strip()]
    excluded_base_assets = [item.strip() for item in str(args.exclude_base_assets).split(",") if item.strip()]
    report = resolve_symbol_exploration(
        client=client,
        data_root=args.data_root,
        limit=args.limit,
        min_quote_volume=args.min_quote_volume,
        excluded_symbols=excluded_symbols,
        excluded_base_assets=excluded_base_assets,
    )
    env_path = args.env_path or None
    write_symbol_exploration_artifacts(report, json_path=args.json_path, env_path=env_path)
    print(json.dumps(report, ensure_ascii=True))
    return 0


def _eligible_usdt_symbols(exchange_info: dict[str, Any]) -> list[str]:
    symbols = exchange_info.get("symbols", [])
    if not isinstance(symbols, list):
        return []

    eligible: list[str] = []
    seen: set[str] = set()
    for item in symbols:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip().upper()
        if not symbol or symbol in seen:
            continue
        if not _is_ascii_alnum_token(symbol):
            continue
        if str(item.get("status", "")).upper() != "TRADING":
            continue
        if str(item.get("quoteAsset", "")).upper() != "USDT":
            continue
        if item.get("isSpotTradingAllowed") is False:
            continue
        seen.add(symbol)
        eligible.append(symbol)
    return eligible


def _symbol_meta_map(exchange_info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    symbols = exchange_info.get("symbols", [])
    if not isinstance(symbols, list):
        return {}

    meta: dict[str, dict[str, Any]] = {}
    for item in symbols:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        meta[symbol] = item
    return meta


def _normalize_symbols(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        symbol = str(value).strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_ascii_alnum_token(value: str) -> bool:
    text = str(value).strip().upper()
    return bool(text) and text.isascii() and text.isalnum()


if __name__ == "__main__":
    raise SystemExit(main())
