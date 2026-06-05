from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


@dataclass(frozen=True)
class BinanceKlineClientConfig:
    base_url: str = "https://fapi.binance.com"
    klines_path: str = "/fapi/v1/klines"
    timeout_sec: float = 5.0


class BinanceKlineClient:
    def __init__(self, config: BinanceKlineClientConfig | None = None) -> None:
        self.config = config or BinanceKlineClientConfig()

    def fetch_klines(self, symbol: str, *, interval: str = "1m", limit: int = 500) -> pd.DataFrame:
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
        return pd.DataFrame(rows)


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
