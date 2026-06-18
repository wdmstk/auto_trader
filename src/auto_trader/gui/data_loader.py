"""Data loading, transformation, and computation functions for the GUI module.

Includes file I/O, data merging, candidate report resolution, and derived
metric computation.  Some functions use ``st.cache_data`` for Streamlit
caching -- these require a running Streamlit context.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import streamlit as st

from auto_trader.analysis.trade_routes import resolve_live_trade_routes
from auto_trader.exchange.rest_client import BinanceRestTransport, RestClientConfig
from auto_trader.gui.state import is_stale
from auto_trader.gui.utils import (
    csv_list,
    format_age,
    freshness_level,
    latest_value,
    now_iso,
    safe_float,
    signal_gate_summary,
    tail_text,
    worker_state_key_parts,
    worker_status_reason,
)
from auto_trader.stateio import atomic_write_json, read_json_with_recovery
from auto_trader.worker.state import WorkerState

DATA_DIR = Path("data")
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
DATA_STALE_WARN_SEC = 30
DATA_STALE_CRIT_SEC = 120
DEFAULT_RUNTIME_METRICS_PATH = DATA_DIR / "validation" / "runtime_metrics.jsonl"
FUTURES_TESTNET_BASE_URL = "https://testnet.binancefuture.com"
FUTURES_TESTNET_ACCOUNT_PATH = "/fapi/v2/account"
REPO_ROOT = Path(__file__).resolve().parents[3]
JOB_STATE_PATH = DATA_DIR / "runtime" / "gui_refresh_job.json"
_GUI_ENV_LOADED = False
_ALLOWED_DATA_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "data",
    Path("data").resolve(),
)


def _is_safe_data_path(path_str: str) -> bool:
    """Validate that a user-supplied path stays within allowed data directories."""
    try:
        resolved = Path(path_str).resolve()
    except (ValueError, OSError):
        return False
    return any(
        resolved == root or str(resolved).startswith(str(root) + os.sep)
        for root in _ALLOWED_DATA_ROOTS
    )


@st.cache_data(ttl=10, show_spinner=False)
def _read_optional_cached(path_str: str) -> pd.DataFrame:
    path = Path(path_str)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()


def _read_optional(path: Path) -> pd.DataFrame:
    try:
        return _read_optional_cached(str(path))
    except Exception:
        if not path.exists():
            return pd.DataFrame()
        try:
            return pd.read_parquet(path)
        except Exception:
            return pd.DataFrame()


def _discover_available_symbols(data_dir: Path = DATA_DIR) -> list[str]:
    symbols: set[str] = set()
    for subdir in ("parquet", "signals", "regime"):
        root = data_dir / subdir
        if not root.exists():
            continue
        for path in root.glob("*"):
            stem = path.stem
            if "_" not in stem:
                continue
            symbol = stem.split("_", 1)[0].strip().upper()
            if symbol:
                symbols.add(symbol)
    ordered = sorted(symbols)
    if ordered:
        return ordered
    return list(DEFAULT_SYMBOLS)


def _discover_symbol_timeframes(symbol: str, data_dir: Path = DATA_DIR) -> list[str]:
    timeframes: set[str] = set()
    symbol = symbol.strip().upper()
    if not symbol:
        return ["1m"]
    for subdir in ("parquet", "signals", "regime"):
        root = data_dir / subdir
        if not root.exists():
            continue
        for path in root.glob(f"{symbol}_*"):
            parts = path.stem.split("_")
            if len(parts) >= 2:
                timeframes.add(parts[1])
    ordered = sorted(timeframes)
    if "1m" in ordered:
        ordered.remove("1m")
        return ["1m", *ordered]
    return ordered or ["1m"]


def _preferred_symbol_choices(limit: int | None = None) -> list[str]:
    available = _discover_available_symbols()
    priority = [symbol for symbol in DEFAULT_SYMBOLS if symbol in available]
    remaining = [symbol for symbol in available if symbol not in priority]
    ordered = [*priority, *remaining]
    if limit is not None and limit > 0:
        return ordered[:limit]
    return ordered


def _core_symbol_focus_rows(candidate_report: Mapping[str, object]) -> list[dict[str, object]]:
    core_symbols_raw = candidate_report.get("core_symbols", [])
    if not isinstance(core_symbols_raw, list) or not core_symbols_raw:
        return []
    core_symbols = [str(symbol).strip().upper() for symbol in core_symbols_raw if str(symbol).strip()]
    best_rows = candidate_report.get("best_by_symbol_strategy", [])
    if not isinstance(best_rows, list) or not best_rows:
        return [{"symbol": symbol, "timeframe": "1m", "strategy": "trend"} for symbol in core_symbols]

    by_symbol: dict[str, dict[str, object]] = {}
    for row in best_rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol", "")).strip().upper()
        if symbol not in core_symbols:
            continue
        current = by_symbol.get(symbol)
        candidate_score = safe_float(row.get("candidate_score", float("-inf")))
        current_score = safe_float(current.get("candidate_score", float("-inf"))) if current else float("-inf")
        if current is None or candidate_score >= current_score:
            by_symbol[symbol] = dict(row)

    rows: list[dict[str, object]] = []
    for symbol in core_symbols:
        row = by_symbol.get(symbol, {})
        rows.append(
            {
                "symbol": symbol,
                "timeframe": str(row.get("timeframe", "1m")).strip() or "1m",
                "strategy": str(row.get("strategy", "trend")).strip() or "trend",
                "candidate_status": str(row.get("candidate_status", "core")).strip() or "core",
                "candidate_score": safe_float(row.get("candidate_score", 0.0)),
                "pf_mean": safe_float(row.get("pf_mean", 0.0)),
                "expectancy_bps_mean": safe_float(row.get("expectancy_bps_mean", 0.0)),
                "monthly_pnl_mean": safe_float(row.get("monthly_pnl_mean", 0.0)),
                "max_dd_mean": safe_float(row.get("max_dd_mean", 0.0)),
            }
        )
    return rows


def _core_symbol_options(candidate_report: Mapping[str, object]) -> list[str]:
    rows = _core_symbol_focus_rows(candidate_report)
    return [str(row["symbol"]) for row in rows if str(row.get("symbol", "")).strip()]


def _read_latest_jsonl_row(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                import json

                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                return payload
    except Exception:
        return {}
    return {}


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _discover_backtest_runs(data_dir: Path = DATA_DIR) -> list[dict[str, object]]:
    backtest_dir = data_dir / "backtest"
    if not backtest_dir.exists():
        return []

    runs: list[dict[str, object]] = []
    for metadata_path in sorted(backtest_dir.glob("**/metadata.json")):
        out_dir = metadata_path.parent
        portfolio_path = out_dir / "portfolio.parquet"
        if not portfolio_path.exists():
            continue
        metadata = _read_json_object(metadata_path)
        generated_at = str(metadata.get("generated_at", "")).strip()
        if generated_at:
            sort_key = pd.to_datetime(generated_at, utc=True, errors="coerce")
        else:
            sort_key = pd.Timestamp(metadata_path.stat().st_mtime, unit="s", tz="UTC")
        symbol = str(metadata.get("symbol", "")).strip().upper() or "UNKNOWN"
        timeframe = str(metadata.get("timeframe", "")).strip() or "unknown"
        strategy = str(metadata.get("strategy", "")).strip() or "unknown"
        label = f"{symbol} {timeframe} {strategy}"
        if generated_at:
            label = f"{label} @ {generated_at}"
        runs.append(
            {
                "label": label,
                "sort_key": sort_key,
                "generated_at": generated_at,
                "symbol": symbol,
                "timeframe": timeframe,
                "strategy": strategy,
                "output_dir": str(out_dir),
                "metadata_path": str(metadata_path),
                "portfolio_path": str(portfolio_path),
            }
        )

    legacy_portfolio = backtest_dir / "portfolio.parquet"
    if legacy_portfolio.exists() and not runs:
        runs.append(
            {
                "label": "legacy data/backtest/portfolio.parquet",
                "sort_key": pd.Timestamp(0, tz="UTC"),
                "generated_at": "",
                "symbol": "UNKNOWN",
                "timeframe": "unknown",
                "strategy": "unknown",
                "output_dir": str(backtest_dir),
                "metadata_path": "",
                "portfolio_path": str(legacy_portfolio),
            }
        )

    runs.sort(key=lambda row: str(row["sort_key"]), reverse=True)
    return runs


def _runtime_health_messages(latest: dict[str, object]) -> tuple[str, list[str]]:
    pending = safe_float(latest.get("gateway_pending_orders", 0.0))
    latency = safe_float(latest.get("order_latency_p95_ms", 0.0))
    blocks = safe_float(latest.get("risk_block_count", 0.0))
    load1 = safe_float(latest.get("system_loadavg_1m", 0.0))
    emergency = bool(latest.get("runtime_emergency_stop", False))
    trading_enabled = bool(latest.get("runtime_trading_enabled", False))

    warnings: list[str] = []
    criticals: list[str] = []

    if emergency:
        criticals.append("EMERGENCY_STOP is active.")
    if not trading_enabled:
        warnings.append("Trading is currently disabled.")
    if pending >= 10:
        criticals.append(f"Pending orders backlog is high ({int(pending)}).")
    elif pending >= 3:
        warnings.append(f"Pending orders backlog is elevated ({int(pending)}).")
    if latency >= 2000:
        criticals.append(f"Order latency p95 is high ({latency:.0f} ms).")
    elif latency >= 500:
        warnings.append(f"Order latency p95 is elevated ({latency:.0f} ms).")
    if blocks >= 10:
        warnings.append(f"Risk blocked count is high ({int(blocks)}).")
    if load1 >= 8.0:
        criticals.append(f"System load average is very high ({load1:.2f}).")
    elif load1 >= 4.0:
        warnings.append(f"System load average is elevated ({load1:.2f}).")

    if criticals:
        return "critical", criticals + warnings
    if warnings:
        return "warning", warnings
    return "ok", ["Runtime metrics are within normal ranges."]



def _load_symbol_regime(
    symbol: str,
    preferred_timeframe: str | None = None,
    regime_dir: Path = DATA_DIR / "regime",
) -> tuple[pd.DataFrame, str]:
    candidates: list[Path] = []
    if preferred_timeframe:
        preferred_path = regime_dir / f"{symbol}_{preferred_timeframe}_regime.parquet"
        if preferred_path.exists():
            candidates.append(preferred_path)
    if regime_dir.exists():
        candidates.extend(path for path in sorted(regime_dir.glob(f"{symbol}_*_regime.parquet")) if path not in candidates)
    for path in candidates:
        frame = _read_optional(path)
        if frame.empty or "regime" not in frame.columns:
            continue
        stem = path.stem.removesuffix("_regime")
        timeframe = preferred_timeframe or "unknown"
        if "_" in stem:
            _, timeframe = stem.rsplit("_", 1)
        return frame, timeframe
    return pd.DataFrame(), preferred_timeframe or "unknown"


def _symbol_snapshot(
    symbol: str,
    risk_df: pd.DataFrame,
    wf_range: dict[str, dict[str, float]],
    wf_trend: dict[str, dict[str, float]],
    *,
    preferred_regime_timeframe: str | None = None,
) -> dict[str, object]:
    regime_df, regime_timeframe = _load_symbol_regime(symbol, preferred_regime_timeframe)
    range_df = _read_optional(DATA_DIR / "signals" / f"{symbol}_1m_range_signals.parquet")
    trend_df = _read_optional(DATA_DIR / "signals" / f"{symbol}_1m_trend_signals.parquet")
    ohlcv_df = _read_optional(DATA_DIR / "parquet" / f"{symbol}_1m.parquet")
    latest_regime = latest_value(regime_df, "regime", default="UNKNOWN")
    last_close: float = float("nan")
    if not ohlcv_df.empty and "close" in ohlcv_df.columns:
        try:
            last_close = float(ohlcv_df.iloc[-1]["close"])
        except Exception:
            last_close = float("nan")
    range_entries = 0
    trend_entries = 0
    if not range_df.empty and "entry_signal" in range_df.columns:
        range_entries = int(pd.to_numeric(range_df["entry_signal"], errors="coerce").fillna(0).astype(bool).sum())
    if not trend_df.empty and "entry_signal" in trend_df.columns:
        trend_entries = int(pd.to_numeric(trend_df["entry_signal"], errors="coerce").fillna(0).astype(bool).sum())
    exposure: float = float("nan")
    dd: float = float("nan")
    vwe: float = float("nan")
    rc: float = float("nan")
    scale: float = float("nan")
    if not risk_df.empty:
        s = risk_df[risk_df.get("symbol", pd.Series(dtype=str)).astype(str) == symbol]
        if not s.empty:
            if "portfolio_exposure_pct" in s.columns:
                exposure = float(pd.to_numeric(s["portfolio_exposure_pct"], errors="coerce").fillna(0.0).iloc[-1])
            if "current_dd_pct" in s.columns:
                dd = float(pd.to_numeric(s["current_dd_pct"], errors="coerce").fillna(0.0).iloc[-1])
            if "vol_weighted_exposure_pct" in s.columns:
                vwe = float(pd.to_numeric(s["vol_weighted_exposure_pct"], errors="coerce").fillna(0.0).iloc[-1])
            if "risk_contribution_pct" in s.columns:
                rc = float(pd.to_numeric(s["risk_contribution_pct"], errors="coerce").fillna(0.0).iloc[-1])
            if "size_scale" in s.columns:
                scale = float(pd.to_numeric(s["size_scale"], errors="coerce").fillna(1.0).iloc[-1])
    pnl = float(wf_range.get(symbol, {}).get("monthly_pnl", 0.0)) + float(wf_trend.get(symbol, {}).get("monthly_pnl", 0.0))
    return {
        "symbol": symbol,
        "regime": latest_regime,
        "regime_timeframe": regime_timeframe,
        "last_close": last_close,
        "range_entries": range_entries,
        "trend_entries": trend_entries,
        "pnl_estimate": pnl,
        "dd_pct": dd,
        "exposure_pct": exposure,
        "vol_weighted_exposure_pct": vwe,
        "risk_contribution_pct": rc,
        "size_scale": scale,
    }


def _latest_symbol_price(symbol: str, *, timeframe: str = "1m") -> float | None:
    price_df = _read_optional(DATA_DIR / "parquet" / f"{symbol}_{timeframe}.parquet")
    if price_df.empty or "close" not in price_df.columns:
        return None
    try:
        return float(pd.to_numeric(price_df["close"], errors="coerce").dropna().iloc[-1])
    except Exception:
        return None


def _resolve_futures_testnet_credentials() -> tuple[str, str]:
    _ensure_gui_env_loaded()
    return (
        os.getenv("BINANCE_FUTURES_TESTNET_API_KEY", ""),
        os.getenv("BINANCE_FUTURES_TESTNET_API_SECRET", ""),
    )


def _ensure_gui_env_loaded() -> None:
    global _GUI_ENV_LOADED
    if _GUI_ENV_LOADED:
        return
    _GUI_ENV_LOADED = True
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        _load_env_file(env_path)
    except Exception:
        return


def _load_env_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


def _exchange_sync_cache_marker() -> str:
    api_key, api_secret = _resolve_futures_testnet_credentials()
    payload = f"{api_key}:{api_secret}:{FUTURES_TESTNET_BASE_URL}:{FUTURES_TESTNET_ACCOUNT_PATH}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _exchange_positions_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=[
                "symbol",
                "position_side",
                "side",
                "position_amt",
                "qty",
                "entry_price",
                "mark_price",
                "unrealized_profit",
                "leverage",
                "margin_type",
                "update_time",
                "update_at",
            ]
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    for col in ["position_amt", "qty", "entry_price", "mark_price", "unrealized_profit"]:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
    if "leverage" in frame.columns:
        frame["leverage"] = pd.to_numeric(frame["leverage"], errors="coerce").fillna(0).astype(int)
    if "update_time" in frame.columns:
        frame["update_time"] = pd.to_numeric(frame["update_time"], errors="coerce").fillna(0).astype(int)
    ordered_cols = [
        "symbol",
        "position_side",
        "side",
        "position_amt",
        "qty",
        "entry_price",
        "mark_price",
        "unrealized_profit",
        "leverage",
        "margin_type",
        "update_time",
        "update_at",
    ]
    for col in ordered_cols:
        if col not in frame.columns:
            frame[col] = "" if col.endswith("_at") or col in {"symbol", "position_side", "side", "margin_type"} else 0.0
    frame = frame[ordered_cols].copy()
    return frame.sort_values(["symbol", "side"], ascending=[True, True]).reset_index(drop=True)


def _local_position_net_frame(position_df: pd.DataFrame) -> pd.DataFrame:
    if position_df.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "local_side",
                "local_net_qty",
                "local_abs_qty",
                "route_count",
                "route_keys",
            ]
        )
    rows: list[dict[str, object]] = []
    frame = position_df.copy()
    if "symbol" not in frame.columns:
        return pd.DataFrame()
    frame["symbol"] = frame["symbol"].astype(str)
    for symbol, group in frame.groupby("symbol", dropna=False):
        signed_qty = 0.0
        abs_qty = 0.0
        route_keys: list[str] = []
        for _, row in group.iterrows():
            side = str(row.get("side", "")).strip().lower()
            qty = safe_float(row.get("qty", 0.0))
            if qty <= 0.0:
                continue
            signed_qty += qty if side == "buy" else -qty
            abs_qty += qty
            route_key = str(row.get("route_key", "")).strip()
            if route_key:
                route_keys.append(route_key)
        if signed_qty > 0.0:
            local_side = "buy"
        elif signed_qty < 0.0:
            local_side = "sell"
        else:
            local_side = "flat"
        rows.append(
            {
                "symbol": str(symbol),
                "local_side": local_side,
                "local_net_qty": signed_qty,
                "local_abs_qty": abs_qty,
                "route_count": int(len(group)),
                "route_keys": ", ".join(sorted(set(route_keys))),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["symbol"], ascending=[True]).reset_index(drop=True)


def _position_reconciliation_frame(
    position_df: pd.DataFrame,
    exchange_position_frame: pd.DataFrame,
) -> pd.DataFrame:
    local_frame = _local_position_net_frame(position_df)
    exchange_frame = exchange_position_frame.copy()
    if local_frame.empty and exchange_frame.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "local_side",
                "local_net_qty",
                "exchange_side",
                "exchange_position_amt",
                "qty_diff",
                "status",
            ]
        )
    if not exchange_frame.empty and "position_amt" in exchange_frame.columns:
        exchange_frame = exchange_frame.rename(columns={"position_amt": "exchange_position_amt", "side": "exchange_side"})
    else:
        exchange_frame = pd.DataFrame(columns=["symbol", "exchange_side", "exchange_position_amt"])
    merged = local_frame.merge(exchange_frame, on="symbol", how="outer")
    for col in ["local_net_qty", "local_abs_qty", "exchange_position_amt"]:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0.0)
    for col in ["local_side", "exchange_side", "route_keys"]:
        if col not in merged.columns:
            merged[col] = ""
        merged[col] = merged[col].fillna("").astype(str)
    merged["qty_diff"] = merged["local_net_qty"] - merged["exchange_position_amt"]
    status: list[str] = []
    for _, row in merged.iterrows():
        local_qty = float(row.get("local_net_qty", 0.0) or 0.0)
        exchange_qty = float(row.get("exchange_position_amt", 0.0) or 0.0)
        if local_qty == 0.0 and exchange_qty == 0.0:
            status.append("flat")
        elif local_qty == exchange_qty:
            status.append("match")
        elif local_qty == 0.0:
            status.append("exchange_only")
        elif exchange_qty == 0.0:
            status.append("local_only")
        else:
            status.append("mismatch")
    merged["status"] = status
    display_cols = [
        "symbol",
        "local_side",
        "local_net_qty",
        "exchange_side",
        "exchange_position_amt",
        "qty_diff",
        "status",
        "route_count",
        "route_keys",
    ]
    for col in display_cols:
        if col not in merged.columns:
            merged[col] = "" if col in {"symbol", "local_side", "exchange_side", "status", "route_keys"} else 0.0
    merged = merged[display_cols].copy()
    return merged.sort_values(["status", "symbol"], ascending=[True, True]).reset_index(drop=True)


def _fetch_exchange_positions_snapshot() -> dict[str, object]:
    api_key, api_secret = _resolve_futures_testnet_credentials()
    if not api_key or not api_secret:
        return {
            "status": "credentials_missing",
            "reason": "BINANCE_FUTURES_TESTNET_API_KEY/SECRET not set",
            "fetched_at": now_iso(),
            "rows": [],
            "frame": _exchange_positions_frame([]),
        }
    transport = BinanceRestTransport(
        RestClientConfig(
            base_url=FUTURES_TESTNET_BASE_URL,
            account_path=FUTURES_TESTNET_ACCOUNT_PATH,
            api_key=api_key,
            api_secret=api_secret,
            sync_server_time=True,
        )
    )
    rows, reason = transport.fetch_account_positions()
    return {
        "status": "ok" if reason == "ok" else "error",
        "reason": reason,
        "fetched_at": now_iso(),
        "rows": rows,
        "frame": _exchange_positions_frame(rows),
    }


@st.cache_data(ttl=15, show_spinner=False)
def _cached_exchange_positions_snapshot(refresh_token: int, cache_marker: str) -> dict[str, object]:
    _ = refresh_token
    _ = cache_marker
    return _fetch_exchange_positions_snapshot()



def _live_pnl_frame(position_df: pd.DataFrame) -> pd.DataFrame:
    if position_df.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "side",
                "qty",
                "avg_entry",
                "mark_price",
                "source_price",
                "unrealized_pnl",
                "unrealized_pnl_pct",
                "position_value",
            ]
        )
    rows: list[dict[str, object]] = []
    for _, row in position_df.iterrows():
        symbol = str(row.get("symbol", ""))
        if not symbol:
            continue
        side = str(row.get("side", "buy"))
        qty = safe_float(row.get("qty", 0.0))
        avg_entry = safe_float(row.get("avg_entry", 0.0))
        if qty <= 0.0:
            continue
        mark_price = _latest_symbol_price(symbol) or avg_entry
        source_price = "market" if mark_price != avg_entry else "avg_entry"
        if avg_entry <= 0.0:
            unrealized_pnl = 0.0
            unrealized_pnl_pct = 0.0
        elif side == "sell":
            unrealized_pnl = (avg_entry - mark_price) * qty
            unrealized_pnl_pct = (avg_entry - mark_price) / avg_entry
        else:
            unrealized_pnl = (mark_price - avg_entry) * qty
            unrealized_pnl_pct = (mark_price - avg_entry) / avg_entry
        rows.append(
            {
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "avg_entry": avg_entry,
                "mark_price": mark_price,
                "source_price": source_price,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "position_value": qty * mark_price,
            }
        )
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    return frame.sort_values(["symbol", "side"], ascending=[True, True]).reset_index(drop=True)


def _live_pnl_summary(position_df: pd.DataFrame) -> dict[str, float]:
    frame = _live_pnl_frame(position_df)
    if frame.empty:
        return {
            "live_unrealized_pnl": 0.0,
            "live_unrealized_pnl_pct": 0.0,
            "position_value": 0.0,
            "cost_basis": 0.0,
        }
    live_unrealized_pnl = float(pd.to_numeric(frame["unrealized_pnl"], errors="coerce").fillna(0.0).sum())
    position_value = float(pd.to_numeric(frame["position_value"], errors="coerce").fillna(0.0).sum())
    cost_basis = float((pd.to_numeric(frame["qty"], errors="coerce").fillna(0.0) * pd.to_numeric(frame["avg_entry"], errors="coerce").fillna(0.0)).sum())
    live_unrealized_pnl_pct = (live_unrealized_pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0
    return {
        "live_unrealized_pnl": live_unrealized_pnl,
        "live_unrealized_pnl_pct": live_unrealized_pnl_pct,
        "position_value": position_value,
        "cost_basis": cost_basis,
    }


def _build_return_matrix(symbols: list[str], max_rows_per_symbol: int = 2000) -> pd.DataFrame:
    closes: dict[str, pd.Series] = {}
    for symbol in symbols:
        ohlcv_df = _read_optional(DATA_DIR / "parquet" / f"{symbol}_1m.parquet")
        if ohlcv_df.empty or "timestamp" not in ohlcv_df.columns or "close" not in ohlcv_df.columns:
            continue
        if max_rows_per_symbol > 0 and len(ohlcv_df) > max_rows_per_symbol:
            ohlcv_df = ohlcv_df.tail(max_rows_per_symbol).copy()
        x = ohlcv_df[["timestamp", "close"]].copy()
        x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
        x = x.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
        x["ret"] = pd.to_numeric(x["close"], errors="coerce").pct_change()
        closes[symbol] = x.set_index("timestamp")["ret"]
    if not closes:
        return pd.DataFrame()
    mat = pd.DataFrame(closes).dropna(how="all")
    return mat


def _read_walkforward_summary(symbol: str, timeframe: str, strategy: str) -> pd.DataFrame:
    # Preferred new naming
    p1 = DATA_DIR / "analysis" / f"walkforward_{symbol}_{timeframe}_{strategy}_summary.parquet"
    df = _read_optional(p1)
    if not df.empty:
        return df
    # Backward compatibility
    p2 = DATA_DIR / "analysis" / f"walkforward_{strategy}_summary.parquet"
    return _read_optional(p2)


def _load_walkforward_metric_map(strategy: str, symbols: list[str], timeframe: str = "1m") -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        df = _read_walkforward_summary(symbol=symbol, timeframe=timeframe, strategy=strategy)
        if df.empty:
            out[symbol] = {"pf": 0.0, "win_rate": 0.0, "max_dd": 0.0, "monthly_pnl": 0.0}
            continue
        pf = float(pd.to_numeric(df.get("pf", pd.Series([0.0])), errors="coerce").fillna(0.0).mean())
        wr = float(pd.to_numeric(df.get("win_rate", pd.Series([0.0])), errors="coerce").fillna(0.0).mean())
        dd = float(pd.to_numeric(df.get("max_dd", pd.Series([0.0])), errors="coerce").fillna(0.0).mean())
        pnl = float(pd.to_numeric(df.get("monthly_pnl", pd.Series([0.0])), errors="coerce").fillna(0.0).mean())
        out[symbol] = {"pf": pf, "win_rate": wr, "max_dd": dd, "monthly_pnl": pnl}
    return out


def _load_walkforward_artifact(symbol: str, timeframe: str, strategy: str, kind: str) -> pd.DataFrame:
    p1 = DATA_DIR / "analysis" / f"walkforward_{symbol}_{timeframe}_{strategy}_{kind}.parquet"
    df = _read_optional(p1)
    if not df.empty:
        return df
    p2 = DATA_DIR / "analysis" / f"walkforward_{strategy}_{kind}.parquet"
    return _read_optional(p2)


def _load_walkforward_metric_map_legacy_removed(strategy: str) -> dict[str, dict[str, float]]:
    # Kept as a stub for compatibility; no longer used.
    return {}



def _read_jsonl_table(path_str: str, tail_rows: int = 200) -> pd.DataFrame:
    path = Path(path_str)
    try:
        return _read_jsonl_table_cached(path_str, tail_rows)
    except Exception:
        if not path.exists():
            return pd.DataFrame()
        try:
            df = pd.read_json(path, lines=True)
        except Exception:
            return pd.DataFrame()
        if tail_rows > 0 and len(df) > tail_rows:
            return df.tail(tail_rows).copy()
        return df


@st.cache_data(ttl=10, show_spinner=False)
def _read_jsonl_table_cached(path_str: str, tail_rows: int = 200) -> pd.DataFrame:
    path = Path(path_str)
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_json(path, lines=True)
    except Exception:
        return pd.DataFrame()
    if tail_rows > 0 and len(df) > tail_rows:
        return df.tail(tail_rows).copy()
    return df


def _load_runtime_state(
    path: Path = DATA_DIR / "runtime" / "control_state.json",
) -> dict[str, object]:
    payload = read_json_with_recovery(path)
    return {
        "trading_enabled": bool(payload.get("trading_enabled", False)),
        "emergency_stop": bool(payload.get("emergency_stop", False)),
        "close_all_requested": bool(payload.get("close_all_requested", False)),
        "updated_at": str(payload.get("updated_at", "")),
    }


def _load_worker_state(path: Path = DATA_DIR / "runtime" / "worker_state.json") -> WorkerState:
    if not path.exists():
        return WorkerState()
    try:
        return WorkerState.load(path)
    except Exception:
        return WorkerState()


def _load_runtime_metrics(path: Path) -> dict[str, object]:
    return _read_latest_jsonl_row(path)


def _route_selection_path() -> Path:
    raw = str(
        os.getenv(
            "ROUTE_SELECTION_PATH",
            os.getenv("WEEKLY_REVALIDATION_REPORT_PATH", ""),
        )
    ).strip()
    if not raw:
        env_path = DATA_DIR / "validation" / "weekly_autotune" / "route_selection_runtime.env"
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    if key.strip() in {"ROUTE_SELECTION_PATH", "WEEKLY_REVALIDATION_REPORT_PATH"}:
                        candidate = value.strip()
                        if candidate:
                            raw = candidate
                            break
            except Exception:
                raw = ""
    return Path(raw) if raw else DATA_DIR / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"


def _weekly_revalidation_report_path() -> Path:
    raw = str(os.getenv("WEEKLY_REVALIDATION_REPORT_PATH", "")).strip()
    if not raw:
        env_path = DATA_DIR / "validation" / "weekly_autotune" / "route_selection_runtime.env"
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    if key.strip() == "WEEKLY_REVALIDATION_REPORT_PATH":
                        candidate = value.strip()
                        if candidate:
                            raw = candidate
                            break
            except Exception:
                raw = ""
    if raw:
        return Path(raw)
    preferred = DATA_DIR / "validation" / "weekly_autotune" / "weekly_revalidation" / "weekly_revalidation_report.json"
    if preferred.exists():
        return preferred
    return DATA_DIR / "validation" / "weekly_revalidation" / "weekly_revalidation_report.json"


def _candidate_payload_from_trade_routes(payload: Mapping[str, object]) -> dict[str, object]:
    selection = payload.get("selection", {})
    routes: object = None
    if isinstance(selection, Mapping):
        routes = selection.get("trade_routes")
    if not isinstance(routes, list) or not routes:
        resolved = resolve_live_trade_routes(cast(dict[str, Any], dict(payload)), default_timeframe="15m")
        routes = resolved.get("trade_routes", [])
    if not isinstance(routes, list) or not routes:
        return {}

    rows: list[dict[str, object]] = []
    best_by_symbol_strategy: list[dict[str, object]] = []
    core_symbols: list[str] = []
    probe_symbols: list[str] = []
    watchlist_symbols: list[str] = []
    status_counts: dict[str, int] = {}

    for item in routes:
        if not isinstance(item, dict):
            continue
        row = {
            "symbol": str(item.get("symbol", "")).strip(),
            "strategy": str(item.get("strategy", "")).strip(),
            "timeframe": str(item.get("timeframe", "")).strip() or "15m",
            "candidate_status": str(item.get("candidate_status", "core")).strip() or "core",
            "pf_mean": safe_float(item.get("pf_mean", 0.0)),
            "expectancy_bps_mean": safe_float(item.get("expectancy_bps_mean", 0.0)),
            "period_pnl_mean": safe_float(item.get("period_pnl_mean", 0.0)),
            "max_dd_mean": safe_float(item.get("max_dd_mean", 0.0)),
            "closed_trades_mean": safe_float(item.get("closed_trades_mean", 0.0)),
            "candidate_score": safe_float(item.get("candidate_score", 0.0)),
            "expected_regime": str(item.get("expected_regime", "")).strip(),
            "statistical_status": str(item.get("statistical_status", "")).strip(),
            "selection_source": str(item.get("selection_source", "")).strip(),
            "selected_stage": str(item.get("selected_stage", "")).strip(),
            "config_label": str(item.get("config_label", "")).strip(),
        }
        if not row["symbol"] or not row["strategy"]:
            continue
        rows.append(row)
        best_by_symbol_strategy.append(dict(row))
        status = str(row["candidate_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        symbol = str(row["symbol"])
        if status == "core":
            core_symbols.append(symbol)
        elif status == "probe":
            probe_symbols.append(symbol)
        elif status == "watchlist":
            watchlist_symbols.append(symbol)

    if not rows:
        return {}

    def unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys([str(v) for v in values if str(v).strip()]))

    return {
        "rows": rows,
        "best_by_symbol_strategy": best_by_symbol_strategy,
        "core_symbols": unique(core_symbols),
        "probe_symbols": unique(probe_symbols),
        "watchlist_symbols": unique(watchlist_symbols),
        "candidate_summary": {"candidate_counts": status_counts},
        "selection": payload.get("selection", {}),
        "source": str(payload.get("source", "")),
    }


def _merge_trade_route_payload(target: dict[str, object], payload: Mapping[str, object]) -> None:
    route_payload = _candidate_payload_from_trade_routes(payload)
    if not route_payload:
        return
    _merge_candidate_payload(target, route_payload)
    for key in ("candidate_summary", "selection", "source"):
        if key in route_payload and key not in target:
            target[key] = route_payload[key]


def _load_candidate_report(
    path: Path = DATA_DIR / "validation" / "timeframe_candidates" / "candidate_report.json",
    weekly_path: Path | None = None,
    route_selection_path: Path | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    if path.exists():
        try:
            raw_payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            raw_payload = {}
        payload = raw_payload if isinstance(raw_payload, dict) else {}

    selected_route_path = route_selection_path or _route_selection_path()
    if selected_route_path.exists():
        try:
            route_payload = json.loads(selected_route_path.read_text(encoding="utf-8"))
        except Exception:
            route_payload = {}
        if isinstance(route_payload, dict):
            _merge_trade_route_payload(payload, route_payload)

    resolved_weekly_path = weekly_path or _weekly_revalidation_report_path()
    if resolved_weekly_path.exists():
        try:
            weekly_payload = json.loads(resolved_weekly_path.read_text(encoding="utf-8"))
        except Exception:
            weekly_payload = {}
        if isinstance(weekly_payload, dict) and "range_probe_candidates" in weekly_payload:
            range_probe = weekly_payload.get("range_probe_candidates", {})
            if isinstance(range_probe, dict):
                payload["range_probe_candidates"] = range_probe
                _merge_candidate_payload(payload, range_probe)
        for key in ("candidate_summary", "decision", "selection", "market_status", "limit_status"):
            if key in weekly_payload:
                payload[key] = weekly_payload[key]
    return payload if isinstance(payload, dict) else {}


def _load_weekly_candidate_report(
    path: Path | None = None,
    route_selection_path: Path | None = None,
) -> dict[str, object]:
    selected_route_path = route_selection_path or _route_selection_path()
    route_payload: dict[str, object] = {}
    if selected_route_path.exists():
        try:
            raw_route_payload = json.loads(selected_route_path.read_text(encoding="utf-8"))
        except Exception:
            raw_route_payload = {}
        if isinstance(raw_route_payload, dict):
            route_payload = _candidate_payload_from_trade_routes(raw_route_payload)
            if route_payload and "selection" not in route_payload:
                route_payload["selection"] = raw_route_payload.get("selection", {})

    resolved_path = path or _weekly_revalidation_report_path()
    if not resolved_path.exists():
        return route_payload
    try:
        raw_payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw_payload, dict):
        return {}

    candidates = raw_payload.get("candidates", {})
    payload = candidates if isinstance(candidates, dict) else {}
    if not payload:
        payload = {}

    range_probe = raw_payload.get("range_probe_candidates", {})
    if isinstance(range_probe, dict):
        payload = dict(payload)
        payload["range_probe_candidates"] = range_probe
        _merge_candidate_payload(payload, range_probe)
    for key in (
        "candidate_summary",
        "decision",
        "selection",
        "market_status",
        "limit_status",
        "manifest_weekly_diff",
        "overview",
        "summary_paths",
        "statistical_qualification",
    ):
        if key in raw_payload:
            payload[key] = raw_payload[key]
    if route_payload:
        _merge_candidate_payload(payload, route_payload)
        for key in ("candidate_summary", "selection", "source"):
            if key in route_payload and key not in payload:
                payload[key] = route_payload[key]
    return payload if isinstance(payload, dict) else {}


def _manifest_weekly_diff_rows(
    weekly_report: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    if not isinstance(weekly_report, Mapping):
        return []
    diff = weekly_report.get("manifest_weekly_diff", {})
    if not isinstance(diff, Mapping):
        return []
    rows = diff.get("rows", [])
    if not isinstance(rows, list):
        return []
    out: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "route": str(row.get("route_key", "")),
                "stage": str(row.get("selected_stage", "")),
                "metrics_match": "yes" if bool(row.get("metric_match", False)) else "no",
                "weekly_statistical": str(row.get("weekly_statistical_status", "")),
                "source_trade_oos_days": safe_float(row.get("source_trade_oos_days", 0.0)),
                "weekly_trade_oos_days": safe_float(row.get("weekly_trade_oos_days", 0.0)),
                "weekly_fold_oos_days": safe_float(row.get("weekly_fold_oos_days", 0.0)),
                "fold_window_drift_days": safe_float(row.get("fold_window_drift_days", 0.0)),
                "closed_trades_mean": safe_float(row.get("closed_trades_mean", 0.0)),
                "statistical_reasons": ", ".join(str(item) for item in row.get("statistical_reasons", []) if str(item).strip())
                if isinstance(row.get("statistical_reasons", []), list)
                else "",
            }
        )
    return out


def _merge_candidate_payload(target: dict[str, object], source: Mapping[str, object]) -> None:
    source_rows = _flatten_candidate_rows(source)
    if source_rows:
        target_rows = target.get("rows", [])
        if not isinstance(target_rows, list):
            target_rows = []
        merged_rows = [row for row in target_rows if isinstance(row, dict)]
        merged_rows.extend(source_rows)
        target["rows"] = merged_rows

    source_best_rows = _flatten_candidate_best_rows(source)
    if source_best_rows:
        target_best_rows = target.get("best_by_symbol_strategy", [])
        if not isinstance(target_best_rows, list):
            target_best_rows = []
        merged_best_rows = [row for row in target_best_rows if isinstance(row, dict)]
        merged_best_rows.extend(source_best_rows)
        target["best_by_symbol_strategy"] = merged_best_rows

    for key in ("core_symbols", "probe_symbols", "watchlist_symbols", "timeframes"):
        source_values = source.get(key, [])
        if (not isinstance(source_values, list) or not source_values) and key == "timeframes":
            timeframe_reports = source.get("timeframe_reports", [])
            if not isinstance(timeframe_reports, list):
                timeframe_reports = []
            source_values = [
                str(report.get("timeframe", "")) for report in timeframe_reports if isinstance(report, dict) and str(report.get("timeframe", "")).strip()
            ]
        if not isinstance(source_values, list) or not source_values:
            continue
        target_values = target.get(key, [])
        if not isinstance(target_values, list):
            target_values = []
        merged_values = list(dict.fromkeys([*(str(v) for v in target_values), *(str(v) for v in source_values)]))
        target[key] = merged_values

    source_timeframe_reports = source.get("timeframe_reports", [])
    if isinstance(source_timeframe_reports, list) and source_timeframe_reports:
        target_reports = target.get("timeframe_reports", [])
        if not isinstance(target_reports, list):
            target_reports = []
        merged_reports = [row for row in target_reports if isinstance(row, dict)]
        merged_reports.extend(row for row in source_timeframe_reports if isinstance(row, dict))
        target["timeframe_reports"] = merged_reports


def _flatten_candidate_rows(report: Mapping[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    primary_rows = report.get("rows", [])
    if isinstance(primary_rows, list):
        rows.extend(row for row in primary_rows if isinstance(row, dict))
    timeframe_reports = report.get("timeframe_reports", [])
    if isinstance(timeframe_reports, list):
        for timeframe_report in timeframe_reports:
            if not isinstance(timeframe_report, Mapping):
                continue
            timeframe = str(timeframe_report.get("timeframe", "")).strip()
            nested_rows = timeframe_report.get("rows", [])
            if isinstance(nested_rows, list):
                for row in nested_rows:
                    if not isinstance(row, dict):
                        continue
                    merged_row = dict(row)
                    if timeframe and not str(merged_row.get("timeframe", "")).strip():
                        merged_row["timeframe"] = timeframe
                    rows.append(merged_row)
    return rows


def _flatten_candidate_best_rows(report: Mapping[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    primary_rows = report.get("best_by_symbol_strategy", [])
    if isinstance(primary_rows, list):
        rows.extend(row for row in primary_rows if isinstance(row, dict))
    timeframe_reports = report.get("timeframe_reports", [])
    if isinstance(timeframe_reports, list):
        for timeframe_report in timeframe_reports:
            if not isinstance(timeframe_report, Mapping):
                continue
            timeframe = str(timeframe_report.get("timeframe", "")).strip()
            nested_rows = timeframe_report.get("best_by_symbol_strategy", [])
            if isinstance(nested_rows, list):
                for row in nested_rows:
                    if not isinstance(row, dict):
                        continue
                    merged_row = dict(row)
                    if timeframe and not str(merged_row.get("timeframe", "")).strip():
                        merged_row["timeframe"] = timeframe
                    rows.append(merged_row)
    return rows



def _load_regime_snapshot(
    regime_dir: Path = DATA_DIR / "regime",
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if not regime_dir.exists():
        return pd.DataFrame()
    for path in sorted(regime_dir.glob("*_regime.parquet")):
        stem = path.stem.removesuffix("_regime")
        if "_" not in stem:
            continue
        symbol, timeframe = stem.rsplit("_", 1)
        frame = _read_optional(path)
        if frame.empty or "regime" not in frame.columns:
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "regime": "UNKNOWN",
                    "updated_at": "",
                    "age": "unknown",
                    "path": str(path),
                }
            )
            continue
        latest_row = frame.iloc[-1]
        updated_at = str(latest_row.get("timestamp", ""))
        rows.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "regime": str(latest_row.get("regime", "UNKNOWN")),
                "updated_at": updated_at,
                "age": format_age(updated_at),
                "path": str(path),
            }
        )
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    severity = {
        "SUSTAINED": 4,
        "HIGH_VOL": 4,
        "SPIKE": 3,
        "TREND": 2,
        "RANGE": 1,
        "UNKNOWN": 0,
    }
    out["severity"] = out["regime"].map(severity).fillna(0).astype(int)
    return out.sort_values(["symbol", "timeframe", "severity"], ascending=[True, True, False]).reset_index(drop=True)


def _active_worker_symbols(worker_state: WorkerState) -> list[str]:
    symbols: set[str] = set()
    for key, result in worker_state.last_results.items():
        _route_name, key_symbol, _ = worker_state_key_parts(str(key))
        symbol = key_symbol
        if isinstance(result, dict):
            route = result.get("route", {})
            if isinstance(route, dict):
                symbol = str(route.get("symbol", symbol)).strip() or symbol
        if symbol:
            symbols.add(symbol)
    for key in worker_state.last_processed_bars:
        _, symbol, _ = worker_state_key_parts(str(key))
        if symbol:
            symbols.add(symbol)
    return sorted(symbols)


def _candidate_frame(report: Mapping[str, object], status: str | None = None) -> pd.DataFrame:
    rows = report.get("rows", [])
    if not isinstance(rows, list) or not rows:
        return pd.DataFrame()
    frame = pd.DataFrame([cast(dict[str, object], row) for row in rows if isinstance(row, dict)])
    if frame.empty:
        return frame
    if status is not None and "candidate_status" in frame.columns:
        frame = frame[frame["candidate_status"].astype(str) == status].copy()
    return frame.reset_index(drop=True)



def _candidate_best_by_symbol(report: Mapping[str, object]) -> dict[str, dict[str, object]]:
    best_rows = report.get("best_by_symbol_strategy", [])
    if not isinstance(best_rows, list):
        return {}
    out: dict[str, dict[str, object]] = {}
    for row in best_rows:
        if not isinstance(row, dict):
            continue
        row_map = cast(dict[str, object], row)
        symbol = str(row_map.get("symbol", "")).strip()
        if not symbol or symbol in out:
            continue
        out[symbol] = row_map
    return out


def _overview_symbol_table(
    *,
    symbols: list[str],
    worker_state: WorkerState,
    risk_df: pd.DataFrame,
    candidate_best: Mapping[str, Mapping[str, object]],
    candidate_status_map: dict[str, str],
    active_symbols: set[str] | None = None,
    watchlist_symbols: set[str] | None = None,
) -> pd.DataFrame:
    worker_frame = _worker_last_results_frame(worker_state)
    worker_lookup = {str(row["symbol"]): cast(dict[str, object], row.to_dict()) for _, row in worker_frame.iterrows() if "symbol" in row}
    last_processed_lookup: dict[str, str] = {}
    for key, value in worker_state.last_processed_bars.items():
        _, symbol, _ = worker_state_key_parts(str(key))
        if symbol:
            last_processed_lookup[str(symbol)] = str(value)

    rows: list[dict[str, object]] = []
    active_symbols = active_symbols or set()
    watchlist_symbols = watchlist_symbols or set()
    for symbol in symbols:
        worker_row = worker_lookup.get(symbol, {})
        best_row = candidate_best.get(symbol, {})
        preferred_regime_timeframe = str(best_row.get("timeframe", "")).strip() or None
        snapshot = _symbol_snapshot(
            symbol,
            risk_df,
            {},
            {},
            preferred_regime_timeframe=preferred_regime_timeframe,
        )
        candidate_status = str(best_row.get("candidate_status") or candidate_status_map.get(symbol, "active"))
        rows.append(
            {
                "symbol": symbol,
                "candidate_status": candidate_status,
                "strategy": str(best_row.get("strategy", "")),
                "timeframe": str(best_row.get("timeframe", "")),
                "pf_mean": safe_float(best_row.get("pf_mean", float("nan"))),
                "expectancy_bps_mean": safe_float(best_row.get("expectancy_bps_mean", float("nan"))),
                "max_dd_mean": safe_float(best_row.get("max_dd_mean", float("nan"))),
                "closed_trades_mean": safe_float(best_row.get("closed_trades_mean", float("nan"))),
                "regime": snapshot["regime"],
                "regime_timeframe": snapshot["regime_timeframe"],
                "why_not_trading": worker_status_reason(worker_row) if worker_row else "worker result unavailable",
                "status": str(worker_row.get("status", "")),
                "trade_status": str(worker_row.get("trade_status", "")),
                "risk_blocked": bool(worker_row.get("risk_blocked", False)),
                "entry_signal": bool(worker_row.get("entry_signal", False)),
                "exit_signal": bool(worker_row.get("exit_signal", False)),
                "add_signal": bool(worker_row.get("add_signal", False)),
                "pass_filter": bool(worker_row.get("pass_filter", False)),
                "reason_codes": str(worker_row.get("reason_codes", "")),
                "last_processed_bar": last_processed_lookup.get(symbol, "-"),
                "last_close": snapshot["last_close"],
                "exposure_pct": snapshot["exposure_pct"],
                "dd_pct": snapshot["dd_pct"],
                "size_scale": snapshot["size_scale"],
                "pnl_estimate": snapshot["pnl_estimate"],
                "vol_weighted_exposure_pct": snapshot["vol_weighted_exposure_pct"],
                "risk_contribution_pct": snapshot["risk_contribution_pct"],
                "route": (
                    "active+watchlist" if symbol in active_symbols and symbol in watchlist_symbols else "active" if symbol in active_symbols else "watchlist"
                ),
            }
        )
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    return out.sort_values(["candidate_status", "symbol"], ascending=[True, True]).reset_index(drop=True)


def _strategy_symbol_table(
    *,
    candidate_rows: pd.DataFrame,
    strategy: str,
    worker_state: WorkerState,
    risk_df: pd.DataFrame,
    candidate_status_map: dict[str, str],
    active_symbols: set[str] | None = None,
    watchlist_symbols: set[str] | None = None,
) -> pd.DataFrame:
    if candidate_rows.empty or "strategy" not in candidate_rows.columns:
        return pd.DataFrame()
    frame = candidate_rows[candidate_rows["strategy"].astype(str) == strategy].copy()
    if frame.empty:
        return pd.DataFrame()

    worker_frame = _worker_last_results_frame(worker_state)
    worker_lookup = {str(row["symbol"]): row.to_dict() for _, row in worker_frame.iterrows() if "symbol" in row}
    last_processed_lookup: dict[str, str] = {}
    for key, value in worker_state.last_processed_bars.items():
        _, symbol, _ = worker_state_key_parts(str(key))
        if symbol:
            last_processed_lookup[str(symbol)] = str(value)

    active_symbols = active_symbols or set()
    watchlist_symbols = watchlist_symbols or set()
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            continue
        worker_row = worker_lookup.get(symbol, {})
        status = str(row.get("candidate_status") or candidate_status_map.get(symbol, "watchlist"))
        preferred_regime_timeframe = str(row.get("timeframe", "")).strip() or None
        snapshot = _symbol_snapshot(
            symbol,
            risk_df,
            {},
            {},
            preferred_regime_timeframe=preferred_regime_timeframe,
        )
        if status == "core":
            reason = signal_gate_summary(cast(Mapping[str, object], worker_row)) if worker_row else "worker result unavailable"
        elif status == "watchlist":
            reason = "watchlist候補"
        elif status == "probe":
            reason = "probe候補"
        else:
            reason = f"{status}候補"
        if symbol in active_symbols and symbol in watchlist_symbols:
            active_label = "active+watchlist"
        elif symbol in active_symbols:
            active_label = "active"
        else:
            active_label = "watchlist"
        rows.append(
            {
                "symbol": symbol,
                "strategy": str(row.get("strategy", strategy)),
                "timeframe": str(row.get("timeframe", "")),
                "candidate_status": status,
                "pf_mean": safe_float(row.get("pf_mean", float("nan"))),
                "expectancy_bps_mean": safe_float(row.get("expectancy_bps_mean", float("nan"))),
                "max_dd_mean": safe_float(row.get("max_dd_mean", float("nan"))),
                "closed_trades_mean": safe_float(row.get("closed_trades_mean", float("nan"))),
                "regime": snapshot["regime"],
                "regime_timeframe": snapshot["regime_timeframe"],
                "why_not_trading": reason,
                "risk_blocked": bool(worker_row.get("risk_blocked", False)),
                "entry_signal": bool(worker_row.get("entry_signal", False)),
                "pass_filter": bool(worker_row.get("pass_filter", False)),
                "last_processed_bar": last_processed_lookup.get(symbol, "-"),
                "exposure_pct": snapshot["exposure_pct"],
                "dd_pct": snapshot["dd_pct"],
                "size_scale": snapshot["size_scale"],
                "trade_status": str(worker_row.get("trade_status", "")),
                "cycle_state": str(worker_row.get("status", "")),
                "route": active_label,
            }
        )
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    return out.sort_values(["candidate_status", "symbol"], ascending=[True, True]).reset_index(drop=True)


def _load_job_state() -> dict[str, object]:
    payload = read_json_with_recovery(JOB_STATE_PATH)
    return payload if isinstance(payload, dict) else {}


def _save_job_state(payload: dict[str, object]) -> None:
    atomic_write_json(JOB_STATE_PATH, payload)


def _run_refresh_job() -> dict[str, object]:
    started_at = datetime.now(UTC).isoformat()
    job_state: dict[str, object] = {
        "status": "running",
        "started_at": started_at,
        "finished_at": "",
        "steps": [],
        "message": "Refreshing risk and runtime metrics.",
    }
    _save_job_state(job_state)

    steps: list[dict[str, object]] = []
    commands: list[tuple[str, list[str]]] = [
        (
            "positions_refresh",
            [
                str(REPO_ROOT / "scripts" / "refresh_positions_from_order_events.sh"),
            ],
        ),
        (
            "risk_input",
            [
                str(REPO_ROOT / "scripts" / "refresh_risk_input_from_positions.sh"),
            ],
        ),
        (
            "risk_eval",
            [
                sys.executable,
                "-m",
                "auto_trader.risk",
                "--input-path",
                str(DATA_DIR / "risk" / "risk_input.parquet"),
                "--output-path",
                str(DATA_DIR / "risk" / "risk_eval.parquet"),
            ],
        ),
    ]

    commands.append(
        (
            "runtime_metrics",
            [
                sys.executable,
                "-m",
                "auto_trader.monitor",
                "--runtime-state-path",
                str(DATA_DIR / "runtime" / "control_state.json"),
                "--gateway-state-path",
                str(DATA_DIR / "exchange" / "gateway_state.json"),
                "--risk-eval-path",
                str(DATA_DIR / "risk" / "risk_eval.parquet"),
                "--order-events-path",
                str(DATA_DIR / "exchange" / "order_events.jsonl"),
                "--output-jsonl",
                str(DEFAULT_RUNTIME_METRICS_PATH),
            ],
        )
    )

    overall_ok = True
    for step_name, command in commands:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        step_record: dict[str, object] = {
            "step": step_name,
            "status": "success" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "stdout": tail_text(completed.stdout),
            "stderr": tail_text(completed.stderr),
        }
        steps.append(step_record)
        _save_job_state(
            {
                **job_state,
                "steps": steps,
                "current_step": step_name,
                "last_returncode": completed.returncode,
                "stdout_tail": step_record["stdout"],
                "stderr_tail": step_record["stderr"],
            }
        )
        if completed.returncode != 0:
            overall_ok = False
            break

    finished_at = datetime.now(UTC).isoformat()
    final_state = {
        **job_state,
        "status": "success" if overall_ok else "failed",
        "finished_at": finished_at,
        "steps": steps,
        "message": ("Refresh job completed successfully." if overall_ok else "Refresh job failed. See stderr_tail."),
    }
    _save_job_state(final_state)
    return final_state


def _format_job_state(job_state: Mapping[str, object]) -> pd.DataFrame:
    steps = job_state.get("steps", [])
    rows: list[dict[str, object]] = []
    if isinstance(steps, list):
        for item in steps:
            if isinstance(item, dict):
                rows.append(
                    {
                        "step": str(item.get("step", "")),
                        "status": str(item.get("status", "")),
                        "returncode": item.get("returncode", ""),
                        "reason": str(item.get("reason", "")),
                    }
                )
    return pd.DataFrame(rows)


def _source_snapshot(
    *,
    name: str,
    path: Path,
    frame: pd.DataFrame | None = None,
    timestamp_column: str | None = None,
) -> dict[str, object]:
    file_age = "-"
    if path.exists():
        file_age = format_age(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC))
    rows = len(frame) if frame is not None else (1 if path.exists() else 0)
    latest_timestamp = "-"
    if frame is not None and timestamp_column and timestamp_column in frame.columns and not frame.empty:
        latest_timestamp = str(frame.iloc[-1][timestamp_column])
    return {
        "source": name,
        "path": str(path),
        "exists": path.exists(),
        "rows": rows,
        "file_age": file_age,
        "latest_timestamp": latest_timestamp,
    }


def _worker_last_results_frame(worker_state: WorkerState) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for key, result in sorted(worker_state.last_results.items()):
        if not isinstance(result, dict):
            continue
        signal = result.get("signal", {})
        if not isinstance(signal, dict):
            signal = {}
        trade = result.get("trade", {})
        if not isinstance(trade, dict):
            trade = {}
        route = result.get("route", {})
        if not isinstance(route, dict):
            route = {}
        route_name, key_symbol, key_timeframe = worker_state_key_parts(str(key))
        symbol = str(route.get("symbol", key_symbol)).strip() or key_symbol
        strategy = str(route.get("strategy", "")).strip()
        if not strategy and route_name in {"trend", "range"}:
            strategy = route_name
        timeframe = str(route.get("timeframe", signal.get("timeframe", key_timeframe))).strip()
        reason_codes = signal.get("reason_codes", [])
        if not isinstance(reason_codes, list):
            reason_codes = []
        rows.append(
            {
                "symbol": symbol,
                "strategy": strategy,
                "timeframe": timeframe,
                "status": str(result.get("status", "")),
                "risk_blocked": bool(result.get("risk_blocked", False)),
                "entry_signal": bool(signal.get("entry_signal", False)),
                "exit_signal": bool(signal.get("exit_signal", False)),
                "add_signal": bool(signal.get("add_signal", False)),
                "pass_filter": bool(signal.get("pass_filter", False)),
                "trade_status": str(trade.get("status", "")),
                "gateway_status": str(trade.get("gateway_status", "")),
                "gateway_reason": str(trade.get("gateway_reason", "")),
                "reason_codes": ", ".join(str(code) for code in reason_codes if str(code)),
            }
        )
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    sort_cols = ["symbol"]
    if "strategy" in frame.columns:
        sort_cols = ["symbol", "strategy", "timeframe"]
    return frame.sort_values(sort_cols).reset_index(drop=True)


def _worker_trade_routes_frame(worker_state: WorkerState) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for key, result in sorted(worker_state.last_results.items()):
        if not isinstance(result, dict):
            continue
        route = result.get("route", {})
        signal = result.get("signal", {})
        if not isinstance(route, dict):
            route = {}
        if not isinstance(signal, dict):
            signal = {}
        route_name, key_symbol, key_timeframe = worker_state_key_parts(key)
        route_symbol = str(route.get("symbol", key_symbol)).strip() or key_symbol
        strategy = str(route.get("strategy", "")).strip()
        if not strategy and route_name in {"trend", "range"}:
            strategy = route_name
        timeframe = str(route.get("timeframe", signal.get("timeframe", key_timeframe))).strip()
        expected_regime = str(route.get("expected_regime", signal.get("expected_regime", ""))).strip()
        candidate_status = str(route.get("candidate_status", "")).strip()
        statistical_status = str(route.get("statistical_status", "")).strip()
        route_policy = str(route.get("route_policy", "")).strip()
        if not route_symbol or not strategy:
            continue
        trade = result.get("trade", {})
        trade_status = str(trade.get("status", "")) if isinstance(trade, dict) else ""
        rows.append(
            {
                "symbol": route_symbol,
                "strategy": strategy,
                "timeframe": timeframe,
                "expected_regime": expected_regime,
                "candidate_status": candidate_status,
                "statistical_status": statistical_status,
                "route_policy": route_policy,
                "status": str(result.get("status", "")),
                "trade_status": trade_status,
                "signal_regime": str(signal.get("regime", "")),
                "entry_signal": bool(signal.get("entry_signal", False)),
                "exit_signal": bool(signal.get("exit_signal", False)),
                "risk_blocked": bool(result.get("risk_blocked", False)),
            }
        )
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    if "strategy" in frame.columns and "timeframe" in frame.columns:
        return frame.sort_values(["strategy", "symbol", "timeframe"]).reset_index(drop=True)
    return frame.sort_values(["symbol"]).reset_index(drop=True)


def _candidate_trade_routes_frame(candidate_report: Mapping[str, object]) -> pd.DataFrame:
    resolved = resolve_live_trade_routes(cast(dict[str, Any], dict(candidate_report)), default_timeframe="15m")
    raw_routes = resolved.get("trade_routes", [])
    if not isinstance(raw_routes, list):
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for item in raw_routes:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip()
        strategy = str(item.get("strategy", "")).strip()
        timeframe = str(item.get("timeframe", "")).strip()
        if not symbol or not strategy:
            continue
        rows.append(
            {
                "symbol": symbol,
                "strategy": strategy,
                "timeframe": timeframe,
                "expected_regime": str(item.get("expected_regime", "")).strip(),
                "candidate_status": str(item.get("candidate_status", "")).strip(),
                "statistical_status": str(item.get("statistical_status", "")).strip(),
                "route_policy": str(item.get("route_policy", "")).strip(),
                "status": "configured",
                "trade_status": "",
                "signal_regime": "",
                "entry_signal": False,
                "exit_signal": False,
                "risk_blocked": False,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["strategy", "symbol", "timeframe"]).reset_index(drop=True)


def _candidate_rollup(candidate_report: Mapping[str, object]) -> dict[str, object]:
    core = csv_list(candidate_report.get("core_symbols", []))
    probe = csv_list(candidate_report.get("probe_symbols", []))
    watchlist = csv_list(candidate_report.get("watchlist_symbols", []))
    summary = candidate_report.get("candidate_summary", {})
    if not isinstance(summary, Mapping):
        summary = {}
    candidate_counts = summary.get("candidate_counts", {})
    if not isinstance(candidate_counts, Mapping):
        candidate_counts = {}
    limit_metrics = candidate_report.get("limit_metrics", {})
    if not isinstance(limit_metrics, Mapping):
        limit_metrics = summary.get("limit_metrics", {})
    if not isinstance(limit_metrics, Mapping):
        limit_metrics = {}
    return {
        "core_symbols": core,
        "probe_symbols": probe,
        "watchlist_symbols": watchlist,
        "core_count": int(candidate_counts.get("core", len(core)) or len(core)),
        "probe_count": int(candidate_counts.get("probe", len(probe)) or len(probe)),
        "watchlist_count": int(candidate_counts.get("watchlist", len(watchlist)) or len(watchlist)),
        "limit_metrics": dict(limit_metrics),
        "status": str(candidate_report.get("status", "unknown")),
    }


def _limit_evidence_frame(candidate_report: Mapping[str, object]) -> pd.DataFrame:
    frame = _candidate_frame(candidate_report)
    if frame.empty:
        return frame
    cols = [
        col
        for col in [
            "symbol",
            "timeframe",
            "strategy",
            "candidate_status",
            "limit_order_count_mean",
            "limit_filled_count_mean",
            "limit_partial_count_mean",
            "limit_expired_count_mean",
            "limit_canceled_count_mean",
            "limit_fill_rate_mean",
            "limit_maker_fill_rate_mean",
            "limit_taker_like_rate_mean",
        ]
        if col in frame.columns
    ]
    return frame[cols].copy() if cols else pd.DataFrame()


def _status_banner(
    runtime_state: dict[str, object],
    worker_state: WorkerState,
    latest_metrics: dict[str, object],
    risk_df: pd.DataFrame,
    risk_input_df: pd.DataFrame,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    criticals: list[str] = []
    if bool(runtime_state.get("emergency_stop", False)):
        criticals.append("EMERGENCY_STOP is active.")
    if not bool(runtime_state.get("trading_enabled", False)):
        warnings.append("Trading is disabled.")
    if freshness_level(worker_state.updated_at) in {"warning", "critical"}:
        warnings.append(f"Worker state is {freshness_level(worker_state.updated_at)}.")
    if latest_metrics and freshness_level(latest_metrics.get("timestamp", "")) in {
        "warning",
        "critical",
    }:
        metrics_level = freshness_level(latest_metrics.get("timestamp", ""))
        warnings.append(f"Runtime metrics are {metrics_level}. Start `auto-trader-monitor.service` " "or rerun `python -m auto_trader.monitor --watch`.")
    if not risk_df.empty and "timestamp" in risk_df.columns:
        ts = pd.to_datetime(risk_df.iloc[-1]["timestamp"], utc=True).to_pydatetime()
        if is_stale(ts, datetime.now(UTC), max_delay_sec=DATA_STALE_WARN_SEC):
            risk_input_age = "unknown"
            if not risk_input_df.empty and "timestamp" in risk_input_df.columns:
                risk_input_age = format_age(risk_input_df.iloc[-1]["timestamp"], now=datetime.now(UTC))
            warnings.append(
                "Risk data is stale. Start `auto-trader-risk-refresh.timer` "
                f"Latest risk input age: {risk_input_age}. "
                "If this stays stale, refresh upstream risk_input first."
            )
    if criticals:
        return "critical", criticals + warnings
    if warnings:
        return "warning", warnings
    return "ok", ["Live data is fresh and trading is eligible."]


def _operator_summary(
    *,
    runtime_state: dict[str, object],
    worker_state: WorkerState,
    latest_metrics: dict[str, object],
    risk_df: pd.DataFrame,
    risk_input_df: pd.DataFrame,
    candidate_report: Mapping[str, object],
) -> dict[str, Any]:
    health_level, health_messages = _status_banner(
        runtime_state=runtime_state,
        worker_state=worker_state,
        latest_metrics=latest_metrics,
        risk_df=risk_df,
        risk_input_df=risk_input_df,
    )
    candidate_rollup = _candidate_rollup(candidate_report)
    decision_payload = candidate_report.get("decision", {})
    if not isinstance(decision_payload, Mapping):
        decision_payload = {}
    market_reason = str(decision_payload.get("market_reason", {}).get("reason", "")) if isinstance(decision_payload.get("market_reason"), Mapping) else ""
    limit_reason = str(decision_payload.get("limit_reason", {}).get("reason", "")) if isinstance(decision_payload.get("limit_reason"), Mapping) else ""
    drift_reason = str(decision_payload.get("drift_reason", {}).get("reason", "")) if isinstance(decision_payload.get("drift_reason"), Mapping) else ""

    if bool(runtime_state.get("emergency_stop", False)):
        next_action = "Emergency stop active. Confirm and clear before resuming."
    elif not bool(runtime_state.get("trading_enabled", False)):
        next_action = "Trading is off. Confirm operator intent and gate state."
    elif health_level == "critical":
        next_action = "Investigate critical runtime or risk conditions first."
    elif health_level == "warning":
        next_action = "Review warnings, then recheck runtime and risk freshness."
    elif str(decision_payload.get("status", candidate_rollup["status"])) == "warn":
        next_action = "Review weekly market/limit reasons and adjust symbol gating."
    else:
        next_action = "Maintain watch and keep weekly revalidation on schedule."

    focus = (
        f"core routes={candidate_rollup['core_count']} "
        f"probe routes={candidate_rollup['probe_count']} "
        f"watchlist routes={candidate_rollup['watchlist_count']}"
    )
    limit_metrics = candidate_rollup.get("limit_metrics", {})
    limit_fill_rate = 0.0
    limit_taker_like_rate = 0.0
    if isinstance(limit_metrics, Mapping):
        limit_fill_rate = safe_float(limit_metrics.get("limit_fill_rate_mean", 0.0))
        limit_taker_like_rate = safe_float(limit_metrics.get("limit_taker_like_rate_mean", 0.0))

    reasons = [msg for msg in [market_reason, limit_reason, drift_reason] if msg]
    if not reasons:
        reasons = health_messages

    return {
        "health_level": health_level,
        "health_messages": health_messages,
        "focus": focus,
        "next_action": next_action,
        "reasons": reasons,
        "limit_fill_rate": limit_fill_rate,
        "limit_taker_like_rate": limit_taker_like_rate,
        "decision_status": str(decision_payload.get("status", candidate_rollup["status"])),
        "candidate_rollup": candidate_rollup,
    }

