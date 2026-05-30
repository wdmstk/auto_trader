from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class StressScenarioConfig:
    volatility_multiplier: float = 2.0
    spread_multiplier: float = 2.0
    liquidity_shock_factor: float = 0.5
    api_timeout_rate: float = 0.1


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
