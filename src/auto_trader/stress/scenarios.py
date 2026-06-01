from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class StressScenarioConfig:
    volatility_multiplier: float = 2.0
    spread_multiplier: float = 2.0
    liquidity_shock_factor: float = 0.5
    api_timeout_rate: float = 0.1
    partial_fill_ratio: float = 0.1
    stale_warn_sec: int = 30
    stale_fail_sec: int = 120
    emergency_cycles: int = 3


def apply_scenario(
    ohlcv_df: pd.DataFrame,
    signals_df: pd.DataFrame,
    scenario_name: str,
    cfg: StressScenarioConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    config = cfg or StressScenarioConfig()
    ohlcv = ohlcv_df.copy()
    sig = signals_df.copy()
    failure_count = 0

    if scenario_name == "volatility_2x":
        ohlcv = _apply_volatility(ohlcv, config.volatility_multiplier)
    elif scenario_name == "flash_crash":
        ohlcv, failure_count = _apply_flash_crash(ohlcv)
    elif scenario_name == "low_liquidity":
        ohlcv, sig = _apply_low_liquidity(ohlcv, sig, config.liquidity_shock_factor)
    elif scenario_name == "spread_widening":
        sig["stress_spread_multiplier"] = config.spread_multiplier
    elif scenario_name == "api_timeout":
        sig, failure_count = _apply_api_timeout(sig, config.api_timeout_rate)
    elif scenario_name == "partial_fill_10pct_cancel":
        sig, failure_count = _apply_partial_fill_cancel(sig, config.partial_fill_ratio)
    elif scenario_name == "silent_ws_stale":
        sig, failure_count = _apply_silent_ws_stale(
            sig,
            stale_warn_sec=config.stale_warn_sec,
            stale_fail_sec=config.stale_fail_sec,
            emergency_cycles=config.emergency_cycles,
        )
    else:
        raise ValueError(f"unsupported scenario: {scenario_name}")

    return ohlcv, sig, failure_count


def _apply_volatility(df: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    out = df.copy()
    mid = out["close"]
    high_diff = (out["high"] - mid) * multiplier
    low_diff = (mid - out["low"]) * multiplier
    out["high"] = mid + high_diff
    out["low"] = mid - low_diff
    return out


def _apply_flash_crash(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    out = df.copy()
    if out.empty:
        return out, 0
    idx = len(out) // 2
    low_value = _to_float(out["low"].iloc[idx])
    close_value = _to_float(out["close"].iloc[idx])
    out.loc[out.index[idx], "low"] = low_value * 0.85
    out.loc[out.index[idx], "close"] = close_value * 0.9
    return out, 1


def _apply_low_liquidity(
    ohlcv_df: pd.DataFrame,
    signals_df: pd.DataFrame,
    liquidity_shock_factor: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ohlcv = ohlcv_df.copy()
    sig = signals_df.copy()
    ohlcv["volume"] = ohlcv["volume"] * liquidity_shock_factor
    # conservative: cancel some entries when liquidity is low
    low_liq_mask = (ohlcv["volume"].rank(pct=True) < 0.2).values
    sig.loc[low_liq_mask, "entry_signal"] = False
    return ohlcv, sig


def _apply_api_timeout(signals_df: pd.DataFrame, timeout_rate: float) -> tuple[pd.DataFrame, int]:
    sig = signals_df.copy()
    n = len(sig)
    timeout_n = int(n * timeout_rate)
    if timeout_n <= 0:
        return sig, 0
    timeout_idx = sig.index[:: max(1, n // timeout_n)][:timeout_n]
    sig.loc[timeout_idx, "entry_signal"] = False
    sig.loc[timeout_idx, "exit_signal"] = False
    return sig, len(timeout_idx)


def _to_float(v: object) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _apply_partial_fill_cancel(
    signals_df: pd.DataFrame,
    partial_fill_ratio: float,
) -> tuple[pd.DataFrame, int]:
    sig = signals_df.copy()
    ratio = max(0.0, min(1.0, float(partial_fill_ratio)))
    if sig.empty:
        return sig, 0
    entry_idx = sig.index[sig.get("entry_signal", pd.Series(False, index=sig.index)).astype(bool)]
    if len(entry_idx) == 0:
        return sig, 0
    idx = entry_idx[0]
    sig["order_event"] = "none"
    sig["filled_qty_ratio"] = 0.0
    sig["canceled_qty_ratio"] = 0.0
    sig["position_reflect_ratio"] = 0.0
    sig.loc[idx, "order_event"] = "partial_then_cancel"
    sig.loc[idx, "filled_qty_ratio"] = ratio
    sig.loc[idx, "canceled_qty_ratio"] = 1.0 - ratio
    sig.loc[idx, "position_reflect_ratio"] = ratio
    return sig, 0


def _apply_silent_ws_stale(
    signals_df: pd.DataFrame,
    *,
    stale_warn_sec: int,
    stale_fail_sec: int,
    emergency_cycles: int,
) -> tuple[pd.DataFrame, int]:
    sig = signals_df.copy()
    if sig.empty:
        return sig, 0
    ts = pd.to_datetime(sig["timestamp"], utc=True, errors="coerce")
    first = ts.iloc[0]
    stale_sec = (ts - first).dt.total_seconds().fillna(0.0)
    sig["stale_latency_sec"] = stale_sec
    sig["stale_level"] = "ok"
    sig.loc[sig["stale_latency_sec"] >= float(stale_warn_sec), "stale_level"] = "warn"
    sig.loc[sig["stale_latency_sec"] >= float(stale_fail_sec), "stale_level"] = "fail"
    sig["emergency_stop"] = False
    fail_mask = sig["stale_level"] == "fail"
    consec = 0
    first_fail_idx: int | None = None
    first_emergency_idx: int | None = None
    for i, is_fail in enumerate(fail_mask.tolist()):
        consec = consec + 1 if is_fail else 0
        if is_fail and first_fail_idx is None:
            first_fail_idx = i
        if consec >= int(emergency_cycles):
            sig.at[sig.index[i], "emergency_stop"] = True
            if first_emergency_idx is None:
                first_emergency_idx = i
    detect_to_stop = 0.0
    if first_fail_idx is not None and first_emergency_idx is not None:
        detect_to_stop = float(
            sig["stale_latency_sec"].iloc[first_emergency_idx]
            - sig["stale_latency_sec"].iloc[first_fail_idx]
        )
    sig["stale_detect_to_stop_latency_sec"] = detect_to_stop
    return sig, int(fail_mask.sum())
