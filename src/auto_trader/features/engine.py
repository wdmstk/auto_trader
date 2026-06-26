from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
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
    recent_low_window: int = 20
    sr_pivot_left_bars: int = 5
    sr_pivot_right_bars: int = 5
    sr_cluster_atr_mult: float = 0.5
    sr_max_levels: int = 10
    sr_level_max_age_bars: int = 500
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
        candle_range = (g2["high"] - g2["low"]).astype("float64")
        candle_range = candle_range.mask(candle_range == 0.0)
        lower_wick = (g2[["open", "close"]].min(axis=1) - g2["low"]).clip(lower=0).astype("float64")
        g2["wick_ratio"] = (lower_wick / candle_range).fillna(0.0)
        bb_mid = g2["close"].rolling(cfg.bb_window).mean()
        bb_std = g2["close"].rolling(cfg.bb_window).std(ddof=0)
        g2["mean_reversion_distance"] = (g2["close"] - bb_mid) / bb_std.replace(0.0, pd.NA)
        bb_lower = bb_mid - 2 * bb_std
        bb_upper = bb_mid + 2 * bb_std
        bb_range = (bb_upper - bb_lower).replace(0.0, pd.NA)
        g2["bb_position"] = ((g2["close"] - bb_lower) / bb_range).fillna(0.5)
        recent_low = g2["low"].rolling(cfg.recent_low_window).min()
        atr_for_norm = g2["atr"] if "atr" in g2.columns else _atr(g2["high"], g2["low"], g2["close"], cfg.atr_window)
        g2["price_vs_recent_low"] = ((g2["close"] - recent_low) / atr_for_norm.replace(0.0, pd.NA)).fillna(0.0)
        g2["volume_spike"] = (g2["volume_ratio"].fillna(1.0) > 1.3).astype(int)
        prev_close = g2["close"].shift(1)
        reversal = (g2["close"] > g2["open"]) & (prev_close > g2["close"])
        g2["reversal_candle_flag"] = reversal.astype(int)

        # S/R level features
        sr_features = _compute_sr_features(
            high=g2["high"].to_numpy(dtype=np.float64, copy=True),
            low=g2["low"].to_numpy(dtype=np.float64, copy=True),
            close=g2["close"].to_numpy(dtype=np.float64, copy=True),
            atr=g2["atr"].to_numpy(dtype=np.float64, copy=True),
            pivot_left=cfg.sr_pivot_left_bars,
            pivot_right=cfg.sr_pivot_right_bars,
            cluster_atr_mult=cfg.sr_cluster_atr_mult,
            max_levels=cfg.sr_max_levels,
            max_age=cfg.sr_level_max_age_bars,
        )
        g2["sr_support_distance"] = sr_features["sr_support_distance"]
        g2["sr_resistance_distance"] = sr_features["sr_resistance_distance"]
        g2["sr_level_strength"] = sr_features["sr_level_strength"]

        # TREND features
        returns = g2["close"].pct_change()
        sign = returns.gt(0).astype(int) - returns.lt(0).astype(int)
        g2["momentum_persistence"] = sign.rolling(cfg.persistence_window).mean().abs()
        rolling_max = g2["close"].shift(1).rolling(cfg.persistence_window).max()
        breakout = (g2["close"] > rolling_max).astype(int)
        g2["breakout_persistence"] = breakout.rolling(cfg.persistence_window).mean()
        rolling_low = g2["low"].rolling(cfg.persistence_window).min()
        g2["pullback_shallowness"] = (g2["close"] - rolling_low) / (rolling_max - rolling_low).replace(0.0, pd.NA)
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
        "bb_position",
        "price_vs_recent_low",
        "volume_spike",
        "reversal_candle_flag",
        "sr_support_distance",
        "sr_resistance_distance",
        "sr_level_strength",
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


def _compute_sr_features(
    *,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr: np.ndarray,
    pivot_left: int,
    pivot_right: int,
    cluster_atr_mult: float,
    max_levels: int,
    max_age: int,
) -> dict[str, np.ndarray]:
    """Compute S/R level features for each bar.

    Returns arrays: sr_support_distance, sr_resistance_distance, sr_level_strength.
    Distances are ATR-normalized.  NaN when no level found.
    """
    n = len(close)
    # Use Python lists for intermediate storage to keep typing simple for mypy
    sr_support_dist: list[float] = [float("nan")] * n
    sr_resistance_dist: list[float] = [float("nan")] * n
    sr_strength: list[float] = [0.0] * n

    # levels: list of (price, strength, last_bar_index)
    levels: list[list[float | int]] = []

    for i in range(n):
        cur_atr = float(atr[i])
        if np.isnan(cur_atr) or cur_atr <= 0:
            continue

        # Detect confirmed pivots (bar at i - pivot_right is the candidate)
        candidate = i - pivot_right
        if candidate >= pivot_left:
            _detect_and_add_pivot(
                high,
                low,
                candidate,
                pivot_left,
                pivot_right,
                levels,
                cur_atr,
                cluster_atr_mult,
            )

        # Expire old levels
        levels = [lv for lv in levels if (i - int(lv[2])) <= max_age]

        # Keep strongest levels only
        if len(levels) > max_levels:
            levels.sort(key=lambda lv: lv[1], reverse=True)
            levels = levels[:max_levels]

        if not levels:
            continue

        cur_close = float(close[i])

        # Find nearest support (levels below close) and resistance (above)
        best_sup_dist = np.inf
        best_sup_strength = 0.0
        best_res_dist = np.inf
        best_res_strength = 0.0

        for lv in levels:
            price = float(lv[0])
            strength = float(lv[1])
            dist = (cur_close - price) / cur_atr

            if dist >= 0:
                # Support: level is below current price
                if dist < best_sup_dist:
                    best_sup_dist = dist
                    best_sup_strength = strength
            else:
                # Resistance: level is above current price
                abs_dist = abs(dist)
                if abs_dist < best_res_dist:
                    best_res_dist = abs_dist
                    best_res_strength = strength

        if best_sup_dist < np.inf:
            sr_support_dist[i] = best_sup_dist
        if best_res_dist < np.inf:
            sr_resistance_dist[i] = best_res_strength

        # Use strength of the nearest level (support preferred for range entry)
        if best_sup_dist <= best_res_dist and best_sup_dist < np.inf:
            sr_strength[i] = best_sup_strength
        elif best_res_dist < np.inf:
            sr_strength[i] = best_res_strength

    return {
        "sr_support_distance": np.array(sr_support_dist, dtype=np.float64),
        "sr_resistance_distance": np.array(sr_resistance_dist, dtype=np.float64),
        "sr_level_strength": np.array(sr_strength, dtype=np.float64),
    }


def _detect_and_add_pivot(
    high: np.ndarray,
    low: np.ndarray,
    candidate: int,
    pivot_left: int,
    pivot_right: int,
    levels: list[list[float | int]],
    cur_atr: float,
    cluster_atr_mult: float,
) -> None:
    """Check if ``candidate`` bar is a swing high or swing low and add to levels."""
    n = len(high)
    left_start = candidate - pivot_left
    right_end = candidate + pivot_right + 1
    if left_start < 0 or right_end > n:
        return

    cand_low = float(low[candidate])
    cand_high = float(high[candidate])

    window_low = low[left_start:right_end]
    window_high = high[left_start:right_end]

    is_swing_low = cand_low <= float(np.min(window_low))
    is_swing_high = cand_high >= float(np.max(window_high))

    cluster_dist = cluster_atr_mult * cur_atr

    if is_swing_low:
        _merge_or_add_level(levels, cand_low, candidate, cluster_dist)
    if is_swing_high:
        _merge_or_add_level(levels, cand_high, candidate, cluster_dist)


def _merge_or_add_level(
    levels: list[list[float | int]],
    price: float,
    bar_index: int,
    cluster_dist: float,
) -> None:
    """Merge into existing level if close enough, otherwise add new."""
    for lv in levels:
        if abs(float(lv[0]) - price) <= cluster_dist:
            # Merge: weighted average price, increment strength, update recency
            old_price = float(lv[0])
            old_strength = float(lv[1])
            new_strength = old_strength + 1
            lv[0] = (old_price * old_strength + price) / new_strength
            lv[1] = new_strength
            lv[2] = bar_index
            return
    levels.append([price, 1.0, float(bar_index)])


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
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
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


def compute_htf_sr_features(
    *,
    htf_high: np.ndarray,
    htf_low: np.ndarray,
    htf_close: np.ndarray,
    htf_timestamps: np.ndarray,
    ltf_close: np.ndarray,
    ltf_atr: np.ndarray,
    ltf_timestamps: np.ndarray,
    pivot_left: int,
    pivot_right: int,
    cluster_atr_mult: float,
    max_levels: int,
    max_age: int,
) -> dict[str, np.ndarray]:
    """Detect S/R levels on HTF data and compute distances for LTF bars.

    Returns dict with keys: sr_support_distance, sr_resistance_distance, sr_level_strength
    Arrays are aligned with ltf_close/ltf_timestamps and distances are normalized by ltf_atr.
    """
    # Ensure numpy arrays
    htf_high = np.asarray(htf_high, dtype=np.float64)
    htf_low = np.asarray(htf_low, dtype=np.float64)
    htf_close = np.asarray(htf_close, dtype=np.float64)
    htf_ts = np.asarray(htf_timestamps)

    ltf_close = np.asarray(ltf_close, dtype=np.float64)
    ltf_atr = np.asarray(ltf_atr, dtype=np.float64)
    ltf_ts = np.asarray(ltf_timestamps)

    n_htf = len(htf_close)
    n_ltf = len(ltf_close)

    # Compute a simple HTF ATR (rolling mean of True Range) with window covering pivot region
    atr_win = max(1, pivot_left + pivot_right + 1)
    prev = np.concatenate(([np.nan], htf_close[:-1]))
    tr = np.maximum.reduce([htf_high - htf_low, np.abs(htf_high - prev), np.abs(htf_low - prev)])
    atr_htf: list[float] = [float("nan")] * n_htf
    for i in range(n_htf):
        start = max(0, i - atr_win + 1)
        window = tr[start : i + 1]
        if window.size == 0:
            atr_htf[i] = np.nan
        else:
            atr_htf[i] = float(np.nanmean(window))

    # Build level history at each HTF bar (list of levels as of that bar)
    levels: list[list[float | int]] = []
    levels_history: list[list[list[float | int]]] = []

    for i in range(n_htf):
        cur_atr = float(atr_htf[i]) if not np.isnan(atr_htf[i]) else np.nan
        # Detect pivot candidate at i - pivot_right
        candidate = i - pivot_right
        if candidate >= pivot_left and not np.isnan(cur_atr) and cur_atr > 0:
            _detect_and_add_pivot(
                htf_high,
                htf_low,
                candidate,
                pivot_left,
                pivot_right,
                levels,
                cur_atr,
                cluster_atr_mult,
            )
        # Expire old levels
        levels = [lv for lv in levels if (i - int(lv[2])) <= max_age]
        # Keep strongest only
        if len(levels) > max_levels:
            levels.sort(key=lambda lv: lv[1], reverse=True)
            levels = levels[:max_levels]
        # Store a deep copy of current levels
        levels_history.append([lv.copy() for lv in levels])

    # For each LTF bar, find corresponding most recent HTF index and compute distances
    sr_support: list[float] = [float("nan")] * n_ltf
    sr_resistance: list[float] = [float("nan")] * n_ltf
    sr_strength: list[float] = [0.0] * n_ltf

    # Convert timestamps to numpy datetime64 for comparison if not already
    try:
        htf_np_ts = htf_ts.astype("datetime64[ns]")
    except Exception:
        htf_np_ts = np.array(htf_ts)
    try:
        ltf_np_ts = ltf_ts.astype("datetime64[ns]")
    except Exception:
        ltf_np_ts = np.array(ltf_ts)

    # For efficient lookup, keep current htf index pointer
    htf_idx = 0
    for j in range(n_ltf):
        ts = ltf_np_ts[j]
        # advance htf_idx while next HTF timestamp <= current LTF ts
        while htf_idx + 1 < n_htf and htf_np_ts[htf_idx + 1] <= ts:
            htf_idx += 1
        # If current HTF timestamp > LTF ts, there is no completed HTF bar yet
        if htf_np_ts[htf_idx] > ts:
            # No levels yet
            continue
        levels_at = levels_history[htf_idx]
        if not levels_at:
            continue
        cur_close = float(ltf_close[j])
        cur_atr = float(ltf_atr[j])
        if np.isnan(cur_atr) or cur_atr <= 0:
            continue
        best_sup_dist = np.inf
        best_sup_strength = 0.0
        best_res_dist = np.inf
        best_res_strength = 0.0
        for lv in levels_at:
            price = float(lv[0])
            strength = float(lv[1])
            dist = (cur_close - price) / cur_atr
            if dist >= 0:
                if dist < best_sup_dist:
                    best_sup_dist = dist
                    best_sup_strength = strength
            else:
                abs_dist = abs(dist)
                if abs_dist < best_res_dist:
                    best_res_dist = abs_dist
                    best_res_strength = strength
        if best_sup_dist < np.inf:
            sr_support[j] = best_sup_dist
        if best_res_dist < np.inf:
            sr_resistance[j] = best_res_dist
        if best_sup_dist <= best_res_dist and best_sup_dist < np.inf:
            sr_strength[j] = best_sup_strength
        elif best_res_dist < np.inf:
            sr_strength[j] = best_res_strength

    return {
        "sr_support_distance": np.array(sr_support, dtype=np.float64),
        "sr_resistance_distance": np.array(sr_resistance, dtype=np.float64),
        "sr_level_strength": np.array(sr_strength, dtype=np.float64),
    }


def overlay_htf_sr(
    features: pd.DataFrame,
    htf_ohlcv: pd.DataFrame,
    ltf_ohlcv: pd.DataFrame,
    config: FeatureConfig,
) -> pd.DataFrame:
    """Overlay HTF-derived S/R values onto LTF feature dataframe.

    Matches by timestamp order; returns a new DataFrame with S/R columns replaced.
    """
    # Prepare arrays from HTF and LTF ohlcv
    htf_high = htf_ohlcv["high"].to_numpy(dtype=np.float64)
    htf_low = htf_ohlcv["low"].to_numpy(dtype=np.float64)
    htf_close = htf_ohlcv["close"].to_numpy(dtype=np.float64)
    htf_ts = htf_ohlcv["timestamp"].to_numpy()

    ltf_close = ltf_ohlcv["close"].to_numpy(dtype=np.float64)
    # Use provided LTF ATR if present in features or compute simple proxy
    if "atr" in features.columns:
        ltf_atr = features["atr"].to_numpy(dtype=np.float64)
    else:
        # Fallback: use rolling range from ltf_ohlcv
        prev = np.concatenate(([np.nan], ltf_close[:-1]))
        tr = np.maximum.reduce(
            [
                ltf_ohlcv["high"].to_numpy(dtype=np.float64) - ltf_ohlcv["low"].to_numpy(dtype=np.float64),
                np.abs(ltf_ohlcv["high"].to_numpy(dtype=np.float64) - prev),
                np.abs(ltf_ohlcv["low"].to_numpy(dtype=np.float64) - prev),
            ]
        )
        # simple window
        win = max(1, config.sr_pivot_left_bars + config.sr_pivot_right_bars + 1)
        ltf_atr = np.array([np.nanmean(tr[max(0, i - win + 1) : i + 1]) for i in range(len(tr))], dtype=np.float64)

    ltf_ts = ltf_ohlcv["timestamp"].to_numpy()

    sr = compute_htf_sr_features(
        htf_high=htf_high,
        htf_low=htf_low,
        htf_close=htf_close,
        htf_timestamps=htf_ts,
        ltf_close=ltf_close,
        ltf_atr=ltf_atr,
        ltf_timestamps=ltf_ts,
        pivot_left=config.sr_pivot_left_bars,
        pivot_right=config.sr_pivot_right_bars,
        cluster_atr_mult=config.sr_cluster_atr_mult,
        max_levels=config.sr_max_levels,
        max_age=config.sr_level_max_age_bars,
    )

    out = features.copy()
    # Ensure target columns exist
    out["sr_support_distance"] = sr["sr_support_distance"]
    out["sr_resistance_distance"] = sr["sr_resistance_distance"]
    out["sr_level_strength"] = sr["sr_level_strength"]
    return out
