from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd


@dataclass(frozen=True)
class FeatureConfig:
    rsi_window: int = 14
    atr_window: int = 14
    bb_window: int = 20
    volume_window: int = 20
    ma_window: int = 20
    trend_eff_window: int = 20
    persistence_window: int = 5
    min_history_bars: int = 50
    feature_version: str = "v1"


def compute_features(
    ohlcv_df: pd.DataFrame,
    config: FeatureConfig | None = None,
) -> pd.DataFrame:
    cfg = config or FeatureConfig()
    required = {
        "symbol",
        "timeframe",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    missing = required.difference(ohlcv_df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    df = ohlcv_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timeframe", "timestamp"]).reset_index(drop=True)
    per_group: list[pd.DataFrame] = []
    for (_, _), g in df.groupby(["symbol", "timeframe"], sort=False):
        g2 = g.copy().reset_index(drop=True)
        g2["rsi"] = _rsi(g2["close"], cfg.rsi_window)
        g2["atr"] = _atr(g2["high"], g2["low"], g2["close"], cfg.atr_window)
        g2["bb_width"] = _bb_width(g2["close"], cfg.bb_window)
        g2["volume_ratio"] = g2["volume"] / g2["volume"].rolling(cfg.volume_window).mean()
        ma = g2["close"].rolling(cfg.ma_window).mean()
        g2["ma_distance"] = (g2["close"] - ma) / ma
        g2["trend_efficiency"] = _trend_efficiency(g2["close"], cfg.trend_eff_window)

        # RANGE features
        candle_range = (g2["high"] - g2["low"]).replace(0.0, pd.NA)
        lower_wick = (g2[["open", "close"]].min(axis=1) - g2["low"]).clip(lower=0)
        g2["wick_ratio"] = (lower_wick / candle_range).fillna(0.0)
        bb_mid = g2["close"].rolling(cfg.bb_window).mean()
        bb_std = g2["close"].rolling(cfg.bb_window).std(ddof=0)
        g2["mean_reversion_distance"] = (g2["close"] - bb_mid) / bb_std.replace(0.0, pd.NA)
        prev_close = g2["close"].shift(1)
        reversal = (g2["close"] > g2["open"]) & (prev_close > g2["close"])
        g2["reversal_candle_flag"] = reversal.astype(int)

        # TREND features
        returns = g2["close"].pct_change()
        sign = returns.gt(0).astype(int) - returns.lt(0).astype(int)
        g2["momentum_persistence"] = sign.rolling(cfg.persistence_window).mean().abs()
        rolling_max = g2["close"].shift(1).rolling(cfg.persistence_window).max()
        breakout = (g2["close"] > rolling_max).astype(int)
        g2["breakout_persistence"] = breakout.rolling(cfg.persistence_window).mean()
        rolling_low = g2["low"].rolling(cfg.persistence_window).min()
        g2["pullback_shallowness"] = (g2["close"] - rolling_low) / (
            rolling_max - rolling_low
        ).replace(0.0, pd.NA)
        higher_high = (g2["high"] > g2["high"].shift(1)).astype(int)
        g2["higher_high_persistence"] = higher_high.rolling(cfg.persistence_window).mean()

        g2["feature_version"] = cfg.feature_version
        g2["generated_at"] = datetime.now(UTC)
        g2["is_warmup"] = g2.index < cfg.min_history_bars
        per_group.append(g2)

    df = pd.concat(per_group, ignore_index=True)

    feature_cols = [
        "symbol",
        "timeframe",
        "timestamp",
        "rsi",
        "atr",
        "bb_width",
        "volume_ratio",
        "ma_distance",
        "trend_efficiency",
        "wick_ratio",
        "mean_reversion_distance",
        "reversal_candle_flag",
        "momentum_persistence",
        "breakout_persistence",
        "pullback_shallowness",
        "higher_high_persistence",
        "feature_version",
        "generated_at",
        "is_warmup",
    ]
    out = df[feature_cols].copy()
    out = out.where(out.notna(), float("nan"))
    return out


def _rsi(close: pd.Series, window: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(
        axis=1
    )
    return tr.rolling(window).mean()


def _bb_width(close: pd.Series, window: int) -> pd.Series:
    ma = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=0)
    upper = ma + 2 * std
    lower = ma - 2 * std
    return (upper - lower) / ma.replace(0.0, pd.NA)


def _trend_efficiency(close: pd.Series, window: int) -> pd.Series:
    direction = (close - close.shift(window)).abs()
    volatility = close.diff().abs().rolling(window).sum()
    return direction / volatility.replace(0.0, pd.NA)
