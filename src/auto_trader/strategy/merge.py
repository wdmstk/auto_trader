from __future__ import annotations

import pandas as pd


def merge_strategy_inputs(
    features_df: pd.DataFrame,
    regime_df: pd.DataFrame,
    risk_df: pd.DataFrame | None = None,
    pnl_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    f = features_df.copy()
    r = regime_df.copy()
    f["timestamp"] = pd.to_datetime(f["timestamp"], utc=True)
    r["timestamp"] = pd.to_datetime(r["timestamp"], utc=True)
    merged = f.merge(r, on=["symbol", "timeframe", "timestamp"], how="inner")

    if risk_df is not None:
        k = risk_df.copy()
        if "timestamp" in k.columns:
            k["timestamp"] = pd.to_datetime(k["timestamp"], utc=True)
            risk_merge_keys: list[str] = ["symbol", "timestamp"]
            if "timeframe" in k.columns:
                risk_merge_keys = ["symbol", "timeframe", "timestamp"]
            merged = merged.merge(k, on=risk_merge_keys, how="left")
    if pnl_df is not None:
        p = pnl_df.copy()
        p["timestamp"] = pd.to_datetime(p["timestamp"], utc=True)
        merged = merged.merge(p, on=["symbol", "timeframe", "timestamp"], how="left")

    if "risk_blocked" not in merged.columns:
        merged["risk_blocked"] = False
    if "unrealized_pnl_pct" not in merged.columns:
        merged["unrealized_pnl_pct"] = 0.0
    merged["risk_blocked"] = merged["risk_blocked"].fillna(False).astype(bool)
    merged["unrealized_pnl_pct"] = merged["unrealized_pnl_pct"].fillna(0.0)
    return merged
