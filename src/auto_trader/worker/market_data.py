from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


@dataclass(frozen=True)
class BinanceKlineClientConfig:
    base_url: str = "https://fapi.binance.com"
    klines_path: str = "/fapi/v1/klines"
    timeout_sec: float = 5.0
    cache_enabled: bool = False
    cache_dir: str = "data/cache/market_data"
    cache_ttl_seconds: int = 60


class BinanceKlineClient:
    def __init__(self, config: BinanceKlineClientConfig | None = None) -> None:
        self.config = config or BinanceKlineClientConfig()
        self._cache_dir = Path(self.config.cache_dir)
        if self.config.cache_enabled:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_errors = 0
        self._api_calls = 0

    def _get_cache_path(self, symbol: str, interval: str) -> Path:
        """Generate cache file path for symbol and interval."""
        safe_symbol = symbol.replace("/", "_")
        return self._cache_dir / f"{safe_symbol}_{interval}.parquet"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache file exists and is within TTL."""
        if not cache_path.exists():
            return False
        try:
            cache_time = datetime.fromtimestamp(cache_path.stat().st_mtime, UTC)
            return datetime.now(UTC) - cache_time < timedelta(seconds=self.config.cache_ttl_seconds)
        except Exception:
            return False

    def _read_cache(self, cache_path: Path) -> pd.DataFrame | None:
        """Read data from cache file with validation."""
        try:
            if not self._is_cache_valid(cache_path):
                self._cache_misses += 1
                return None

            cached_data = pd.read_parquet(cache_path)
            if not cached_data.empty:
                self._cache_hits += 1
                return cached_data
            else:
                self._cache_misses += 1
                return None
        except Exception:
            self._cache_errors += 1
            return None

    def _write_cache(self, cache_path: Path, data: pd.DataFrame) -> None:
        """Write data to cache file."""
        try:
            if self.config.cache_enabled:
                data.to_parquet(cache_path, index=False)
        except Exception:
            # Cache write failure is not critical
            pass

    def fetch_klines(self, symbol: str, *, interval: str = "1m", limit: int = 500) -> pd.DataFrame:
        """Fetch klines with optional caching."""
        cache_path = self._get_cache_path(symbol, interval)

        # Try to load from cache if enabled
        if self.config.cache_enabled:
            cached_data = self._read_cache(cache_path)
            if cached_data is not None and len(cached_data) >= limit:
                return cached_data.tail(limit).copy()

        # Fetch from API
        self._api_calls += 1
        endpoint = self.config.base_url.rstrip("/") + self.config.klines_path
        params = urlencode({"symbol": symbol, "interval": interval, "limit": limit})
        req = Request(f"{endpoint}?{params}", method="GET")
        with urlopen(req, timeout=self.config.timeout_sec) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError("invalid klines payload")
        rows = []
        for item in payload:
            if not isinstance(item, list) or len(item) < 7:
                continue
            open_time = int(item[0])
            close_time = int(item[6]) if len(item) > 6 else open_time
            rows.append(
                {
                    "timestamp": pd.to_datetime(close_time, unit="ms", utc=True),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                    "open_time": pd.to_datetime(open_time, unit="ms", utc=True),
                    "close_time": pd.to_datetime(close_time, unit="ms", utc=True),
                }
            )

        df = pd.DataFrame(rows)

        # Update cache
        self._write_cache(cache_path, df)

        return df

    def get_cache_metrics(self) -> dict[str, Any]:
        """Get cache performance metrics."""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total_requests if total_requests > 0 else 0.0
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_errors": self._cache_errors,
            "cache_hit_rate": hit_rate,
            "api_calls": self._api_calls,
        }

    def clear_cache(self) -> None:
        """Clear all cache files."""
        try:
            if self._cache_dir.exists():
                for cache_file in self._cache_dir.glob("*.parquet"):
                    cache_file.unlink()
        except Exception:
            pass


def resample_ohlcv(ohlcv_1m: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    rule_map = {"5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h"}
    if timeframe not in rule_map:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    if ohlcv_1m.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    frame = ohlcv_1m.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp")
    res = (
        frame.set_index("timestamp")
        .resample(rule_map[timeframe], label="right", closed="right")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    return res[["timestamp", "open", "high", "low", "close", "volume"]].copy()
