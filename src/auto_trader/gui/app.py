from __future__ import annotations

import hashlib

# mypy: disable-error-code=misc
import importlib
import json
import math
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast

import pandas as pd
import streamlit as st

try:
    alt: Any = importlib.import_module("altair")
except Exception:  # pragma: no cover - UI fallback
    alt = None

from auto_trader.analysis.trade_routes import resolve_live_trade_routes
from auto_trader.exchange.rest_client import BinanceRestTransport, RestClientConfig
from auto_trader.gui.overlay import build_overlay_frame, build_regime_segments
from auto_trader.gui.state import ControlEvent, append_control_event, emergency_badge, is_stale
from auto_trader.stateio import atomic_write_json, read_json_with_recovery
from auto_trader.worker.state import WorkerState

DATA_DIR = Path("data")
CONTROL_LOG = DATA_DIR / "gui" / "control_events.jsonl"
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
AUTO_REFRESH_SEC = 10.0
DATA_STALE_WARN_SEC = 30
DATA_STALE_CRIT_SEC = 120
DEFAULT_RUNTIME_METRICS_PATH = DATA_DIR / "validation" / "runtime_metrics.jsonl"
FUTURES_TESTNET_BASE_URL = "https://testnet.binancefuture.com"
FUTURES_TESTNET_ACCOUNT_PATH = "/fapi/v2/account"
REPO_ROOT = Path(__file__).resolve().parents[3]
JOB_STATE_PATH = DATA_DIR / "runtime" / "gui_refresh_job.json"
_GUI_ENV_LOADED = False

_STREAMLIT_DATAFRAME: Any = st.dataframe
_P = ParamSpec("_P")
_T = TypeVar("_T")


def _inject_ui_stability_styles() -> None:
    st.markdown(
        """
        <style>
        /* Keep reload/rerun states from washing out the dashboard text
           without overriding the active theme colors. */
        .stApp,
        .stApp * {
            opacity: 1 !important;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: auto;
        }

        [data-testid="stAppViewContainer"],
        [data-testid="stHeader"],
        [data-testid="stSidebar"] {
            opacity: 1 !important;
        }

        /* Improve visual hierarchy and spacing */
        .stMetric {
            background-color: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 10px;
            margin: 5px 0;
        }

        /* Enhanced button styling for emergency controls */
        div[data-testid="stButton"] > button[kind="danger"] {
            background-color: #ef4444;
            color: white;
            border: 2px solid #dc2626;
        }

        div[data-testid="stButton"] > button[kind="warning"] {
            background-color: #f59e0b;
            color: white;
            border: 2px solid #d97706;
        }

        /* Improve data frame readability */
        .dataframe {
            font-size: 0.9em;
        }

        /* Better expander styling */
        .streamlit-expanderHeader {
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _dataframe(*args: object, **kwargs: object) -> Any:
    use_container_width = kwargs.pop("use_container_width", None)
    if "width" not in kwargs and use_container_width is not None:
        kwargs["width"] = "stretch" if use_container_width else "content"
    return _STREAMLIT_DATAFRAME(*args, **kwargs)


st.dataframe = _dataframe


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
        candidate_score = _safe_float(row.get("candidate_score", float("-inf")))
        current_score = _safe_float(current.get("candidate_score", float("-inf"))) if current else float("-inf")
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
                "candidate_score": _safe_float(row.get("candidate_score", 0.0)),
                "pf_mean": _safe_float(row.get("pf_mean", 0.0)),
                "expectancy_bps_mean": _safe_float(row.get("expectancy_bps_mean", 0.0)),
                "monthly_pnl_mean": _safe_float(row.get("monthly_pnl_mean", 0.0)),
                "max_dd_mean": _safe_float(row.get("max_dd_mean", 0.0)),
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


def _safe_float(v: object, default: float = 0.0) -> float:
    if isinstance(v, bool):
        return float(int(v))
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return default
    return default


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
    pending = _safe_float(latest.get("gateway_pending_orders", 0.0))
    latency = _safe_float(latest.get("order_latency_p95_ms", 0.0))
    blocks = _safe_float(latest.get("risk_block_count", 0.0))
    load1 = _safe_float(latest.get("system_loadavg_1m", 0.0))
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


def _latest_value(df: pd.DataFrame, col: str, default: str = "-") -> str:
    if df.empty or col not in df.columns:
        return default
    return str(df.iloc[-1][col])


def _worker_state_key_parts(key: str) -> tuple[str, str, str]:
    parts = [part for part in str(key).split(":") if part]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1], ""
    if len(parts) == 1:
        return "", parts[0], ""
    return "", "", ""


def _render_persistent_status_banner(
    *,
    runtime_state: dict[str, object],
    worker_state: WorkerState,
    runtime_metrics: dict[str, object],
    risk_df: pd.DataFrame,
) -> None:
    """Render a persistent status banner that shows current system state prominently."""

    # Determine current state level
    emergency_stop = bool(runtime_state.get("emergency_stop", False))
    trading_enabled = bool(runtime_state.get("trading_enabled", False))

    # Get latest regime for additional context
    latest_regime = "UNKNOWN"
    if not risk_df.empty and "regime" in risk_df.columns:
        latest_regime = str(risk_df.iloc[-1]["regime"])

    # Determine banner color and message based on state
    if emergency_stop:
        banner_color = "🔴"  # Red for emergency
        state_message = "EMERGENCY STOP ACTIVE - Trading halted"
        st.error(f"{banner_color} {state_message}")
    elif latest_regime in {"HIGH_VOL", "SUSTAINED"}:
        banner_color = "🟠"  # Orange for high volatility
        state_message = f"HIGH VOLATILITY DETECTED - Regime: {latest_regime}"
        st.warning(f"{banner_color} {state_message}")
    elif latest_regime == "SPIKE":
        banner_color = "🟡"  # Yellow for spike
        state_message = f"PRICE SPIKE DETECTED - Regime: {latest_regime}"
        st.warning(f"{banner_color} {state_message}")
    elif not trading_enabled:
        banner_color = "🔵"  # Blue for trading disabled
        state_message = "TRADING DISABLED - System in standby mode"
        st.info(f"{banner_color} {state_message}")
    else:
        banner_color = "🟢"  # Green for normal operation
        state_message = f"NORMAL OPERATION - Regime: {latest_regime}, Trading: ENABLED"
        st.success(f"{banner_color} {state_message}")

    # Add timestamp and additional context
    if runtime_state.get("updated_at"):
        updated_time = runtime_state["updated_at"]
        st.caption(f"State updated at: {updated_time} | Worker: {worker_state.updated_at}")


def _render_controls() -> None:
    st.subheader("Controls")

    # Separate normal controls from emergency controls for better visual hierarchy
    col1, col2 = st.columns(2)
    normal_buttons = [
        ("START", col1),
        ("STOP", col2),
    ]

    for action, col in normal_buttons:
        if col.button(action, type="primary", use_container_width=True):
            now = datetime.now(UTC)
            append_control_event(
                CONTROL_LOG,
                ControlEvent(
                    action=action,  # type: ignore[arg-type]
                    requested_at=now,
                    applied_at=now,
                    result="accepted",
                ),
            )
            st.success(f"{action} recorded")

    st.markdown("---")  # Visual separator

    # Emergency controls with confirmation dialogs
    st.subheader("Emergency Controls", help="These actions require confirmation")
    col3, col4, col5 = st.columns(3)
    emergency_buttons = [
        ("EMERGENCY_STOP", col3, "⛔ EMERGENCY STOP - This will immediately halt all trading activity", "danger"),
        ("EMERGENCY_CANCEL", col4, "🔄 EMERGENCY CANCEL - This will cancel the emergency stop state", "warning"),
        ("CLOSE_ALL", col5, "❌ CLOSE ALL - This will close all positions immediately", "danger"),
    ]

    for action, col, help_text, button_type in emergency_buttons:
        # Streamlit supports 'danger' and 'warning' types but mypy stubs don't include them
        button_kwargs: dict[str, object] = {"use_container_width": True, "help": help_text}
        if button_type in ("danger", "warning"):
            button_kwargs["type"] = button_type
        if col.button(action, **button_kwargs):
            # Show confirmation dialog for emergency operations
            if st.session_state.get(f"confirmed_{action}", False):
                now = datetime.now(UTC)
                append_control_event(
                    CONTROL_LOG,
                    ControlEvent(
                        action=action,  # type: ignore[arg-type]
                        requested_at=now,
                        applied_at=now,
                        result="accepted",
                    ),
                )
                st.success(f"{action} recorded")
                st.session_state[f"confirmed_{action}"] = False
            else:
                st.session_state[f"confirmed_{action}"] = True
                st.warning(f"⚠️ CONFIRMATION REQUIRED: {help_text}")
                st.button(f"Confirm {action}", type="primary", key=f"confirm_{action}")


def _render_candlestick_overlay(overlay: pd.DataFrame) -> None:
    if overlay.empty:
        st.info("Overlay data unavailable")
        return
    frame = overlay.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    # Fallback for legacy/partial datasets that do not have OHLC columns.
    if "open" not in frame.columns:
        frame["open"] = frame["close"]
    if "high" not in frame.columns:
        frame["high"] = frame["close"]
    if "low" not in frame.columns:
        frame["low"] = frame["close"]

    if alt is None:
        st.line_chart(frame.set_index("timestamp")[["close", "entry_marker", "exit_marker"]])
        st.caption("Altair unavailable. Fallback line chart is shown.")
        return

    frame["up"] = (frame["close"] >= frame["open"]).map({True: "UP", False: "DOWN"})
    regime_segments = build_regime_segments(frame)

    price_span = (pd.to_numeric(frame["high"], errors="coerce") - pd.to_numeric(frame["low"], errors="coerce")).abs()
    price_anchor = pd.to_numeric(frame["close"], errors="coerce").abs()
    fallback_gap = (price_anchor * 0.003).clip(lower=0.05)
    marker_gap = pd.Series(
        [max(float(a) if pd.notna(a) else 0.0, float(b) if pd.notna(b) else 0.0) for a, b in zip(price_span * 0.15, fallback_gap, strict=True)],
        index=frame.index,
    )
    frame["buy_y"] = pd.to_numeric(frame["low"], errors="coerce") - marker_gap
    frame["sell_y"] = pd.to_numeric(frame["high"], errors="coerce") + marker_gap
    frame["risk_y"] = pd.to_numeric(frame["high"], errors="coerce") + (marker_gap * 1.8)

    regime_colors = {
        "RANGE": "#0ea5e9",
        "TREND": "#10b981",
        "SPIKE": "#f59e0b",
        "SUSTAINED": "#ef4444",
        "HIGH_VOL": "#ef4444",
        "UNKNOWN": "#94a3b8",
    }

    background = (
        alt.Chart(regime_segments)
        .mark_rect(opacity=0.16)
        .encode(
            x=alt.X("start:T"),
            x2="end:T",
            color=alt.Color(
                "regime:N",
                scale=alt.Scale(
                    domain=["RANGE", "TREND", "SPIKE", "SUSTAINED", "HIGH_VOL", "UNKNOWN"],
                    range=[
                        regime_colors["RANGE"],
                        regime_colors["TREND"],
                        regime_colors["SPIKE"],
                        regime_colors["SUSTAINED"],
                        regime_colors["HIGH_VOL"],
                        regime_colors["UNKNOWN"],
                    ],
                ),
                legend=alt.Legend(title="regime"),
            ),
        )
        if not regime_segments.empty
        else None
    )

    candle = (
        alt.Chart(frame)
        .mark_bar(size=11)
        .encode(
            x=alt.X("timestamp:T", title="timestamp"),
            y=alt.Y("open:Q", title="price"),
            y2="close:Q",
            color=alt.Color("up:N", scale=alt.Scale(domain=["UP", "DOWN"], range=["#16a34a", "#dc2626"])),
            tooltip=[
                "timestamp:T",
                "open:Q",
                "high:Q",
                "low:Q",
                "close:Q",
                "regime:N",
                "pass_filter:N",
            ],
        )
    )
    wick = (
        alt.Chart(frame)
        .mark_rule(color="#475569")
        .encode(
            x="timestamp:T",
            y="low:Q",
            y2="high:Q",
        )
    )
    entries = (
        alt.Chart(frame[frame["entry_signal"]])
        .mark_point(shape="triangle-up", color="#2563eb", size=110)
        .encode(
            x="timestamp:T",
            y=alt.Y("buy_y:Q", title="price"),
            tooltip=["timestamp:T", "buy_y:Q", "close:Q", "regime:N", "pass_filter:N"],
        )
    )
    entry_labels = (
        alt.Chart(frame[frame["entry_signal"]])
        .mark_text(color="#2563eb", dy=-10, fontSize=11, fontWeight="bold")
        .encode(x="timestamp:T", y="buy_y:Q", text=alt.value("Buy"))
    )
    exits = (
        alt.Chart(frame[frame["exit_signal"]])
        .mark_point(shape="triangle-down", color="#ea580c", size=110)
        .encode(
            x="timestamp:T",
            y=alt.Y("sell_y:Q", title="price"),
            tooltip=["timestamp:T", "sell_y:Q", "close:Q", "regime:N", "pass_filter:N"],
        )
    )
    exit_labels = (
        alt.Chart(frame[frame["exit_signal"]])
        .mark_text(color="#ea580c", dy=12, fontSize=11, fontWeight="bold")
        .encode(x="timestamp:T", y="sell_y:Q", text=alt.value("Sell"))
    )
    risk_block = (
        alt.Chart(frame[frame["risk_blocked"]])
        .mark_point(shape="cross", color="#7c3aed", size=90)
        .encode(
            x="timestamp:T",
            y=alt.Y("risk_y:Q", title="price"),
            tooltip=["timestamp:T", "risk_y:Q", "close:Q", "risk_blocked:N", "pass_filter:N"],
        )
    )
    risk_labels = (
        alt.Chart(frame[frame["risk_blocked"]])
        .mark_text(color="#7c3aed", dy=14, fontSize=11, fontWeight="bold")
        .encode(x="timestamp:T", y="risk_y:Q", text=alt.value("Risk"))
    )
    layers = [
        layer
        for layer in [
            background,
            wick,
            candle,
            entries,
            entry_labels,
            exits,
            exit_labels,
            risk_block,
            risk_labels,
        ]
        if layer is not None
    ]
    chart = alt.layer(*layers).properties(height=780).interactive(bind_x=True, bind_y=True)
    st.altair_chart(chart, use_container_width=True)
    st.caption("Blue up arrow = Buy/entry, orange down arrow = Sell/exit, purple cross = risk block.")


def _downsample_for_chart(df: pd.DataFrame, max_points: int) -> pd.DataFrame:
    if max_points <= 0 or len(df) <= max_points:
        return df
    special_mask = pd.Series(False, index=df.index)
    for col in ("entry_signal", "exit_signal", "risk_blocked"):
        if col in df.columns:
            special_mask |= pd.to_numeric(df[col], errors="coerce").fillna(0).astype(bool)
    special = df[special_mask].copy()
    remaining = df[~special_mask].copy()
    budget = max_points - len(special)
    if budget <= 0:
        sampled = special.tail(max_points).copy()
    else:
        step = max(1, math.ceil(len(remaining) / budget)) if len(remaining) > budget else 1
        sampled = pd.concat([special, remaining.iloc[::step].copy()], axis=0)
    if sampled.index[-1] != df.index[-1]:
        sampled = pd.concat([sampled, df.tail(1)], axis=0)
    sampled = sampled[~sampled.index.duplicated(keep="last")].sort_index()
    return sampled


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
    latest_regime = _latest_value(regime_df, "regime", default="UNKNOWN")
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


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


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
            qty = _safe_float(row.get("qty", 0.0))
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
            "fetched_at": _now_iso(),
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
        "fetched_at": _now_iso(),
        "rows": rows,
        "frame": _exchange_positions_frame(rows),
    }


@st.cache_data(ttl=15, show_spinner=False)
def _cached_exchange_positions_snapshot(refresh_token: int, cache_marker: str) -> dict[str, object]:
    _ = refresh_token
    _ = cache_marker
    return _fetch_exchange_positions_snapshot()


def _render_exchange_position_sync(position_df: pd.DataFrame) -> None:
    st.subheader("Exchange Position Sync")
    st.caption(
        "Binance Futures testnet account endpoint を直接読んで、local positions と "
        "exchange 正本を比較します。route metadata は REST では取得できないため、"
        "比較は symbol net で行います。"
    )
    refresh_key = "exchange_position_refresh_token"
    if refresh_key not in st.session_state:
        st.session_state[refresh_key] = 0
    sync_cols = st.columns([1, 2, 2])
    if sync_cols[0].button("Refresh exchange positions", key="exchange_position_refresh_button"):
        st.session_state[refresh_key] = int(st.session_state[refresh_key]) + 1
    sync_snapshot = _cached_exchange_positions_snapshot(
        int(st.session_state[refresh_key]),
        _exchange_sync_cache_marker(),
    )
    sync_reason = str(sync_snapshot.get("reason", ""))
    sync_status = str(sync_snapshot.get("status", ""))
    sync_fetched_at = str(sync_snapshot.get("fetched_at", ""))
    sync_cols[1].metric("Sync status", sync_status)
    sync_cols[2].metric("Fetched at", sync_fetched_at or "-")
    st.caption(f"sync_reason={sync_reason}")
    exchange_frame = cast(pd.DataFrame, sync_snapshot.get("frame", pd.DataFrame()))
    if sync_status != "ok" and sync_reason == "credentials_missing":
        st.warning("BINANCE_FUTURES_TESTNET_API_KEY/SECRET が未設定のため exchange sync は無効です。")
    elif sync_status != "ok":
        st.warning(f"Exchange sync failed: {sync_reason}")
    if exchange_frame.empty:
        st.info("No exchange positions found.")
    else:
        exchange_display_cols = [
            col
            for col in [
                "symbol",
                "side",
                "position_amt",
                "qty",
                "entry_price",
                "mark_price",
                "unrealized_profit",
                "leverage",
                "margin_type",
                "update_at",
            ]
            if col in exchange_frame.columns
        ]
        st.dataframe(exchange_frame[exchange_display_cols], width="stretch", hide_index=True)

    reconciliation_frame = _position_reconciliation_frame(position_df, exchange_frame)
    if reconciliation_frame.empty:
        st.info("No reconciliation rows available yet.")
    else:
        st.dataframe(reconciliation_frame, width="stretch", hide_index=True)


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
        qty = _safe_float(row.get("qty", 0.0))
        avg_entry = _safe_float(row.get("avg_entry", 0.0))
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


def _render_multi_symbol_panel() -> None:
    st.subheader("Multi-Symbol Panel")
    if not st.checkbox("Enable Multi-Symbol Panel", value=False, key="enable_multi_symbol_panel"):
        st.caption("Disabled for performance. Enable when needed.")
        return
    symbols_raw = st.text_input(
        "Symbols (comma separated)",
        value=",".join(_preferred_symbol_choices(limit=12)),
        key="symbols_input",
    )
    max_symbols = st.slider("Max symbols to render", min_value=2, max_value=20, value=8, step=1)
    enable_heavy = st.checkbox("Enable heavy visualizations (correlation/walkforward tables)", value=False)
    corr_rows = st.slider("Rows per symbol for correlation", min_value=300, max_value=5000, value=1500, step=100)
    symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
    symbols = symbols[:max_symbols]
    if not symbols:
        st.info("No symbols configured")
        return

    wf_range = _load_walkforward_metric_map("range", symbols, timeframe="1m")
    wf_trend = _load_walkforward_metric_map("trend", symbols, timeframe="1m")
    risk_df = _read_optional(DATA_DIR / "risk" / "risk_eval.parquet")
    rows = [_symbol_snapshot(s, risk_df, wf_range, wf_trend) for s in symbols]
    snap = pd.DataFrame(rows)
    snap["wf_range_pf"] = snap["symbol"].map(lambda s: wf_range.get(str(s), {}).get("pf", 0.0))
    snap["wf_range_win_rate"] = snap["symbol"].map(lambda s: wf_range.get(str(s), {}).get("win_rate", 0.0))
    snap["wf_range_max_dd"] = snap["symbol"].map(lambda s: wf_range.get(str(s), {}).get("max_dd", 0.0))
    snap["wf_range_monthly_pnl"] = snap["symbol"].map(lambda s: wf_range.get(str(s), {}).get("monthly_pnl", 0.0))
    snap["wf_trend_pf"] = snap["symbol"].map(lambda s: wf_trend.get(str(s), {}).get("pf", 0.0))
    snap["wf_trend_win_rate"] = snap["symbol"].map(lambda s: wf_trend.get(str(s), {}).get("win_rate", 0.0))
    snap["wf_trend_max_dd"] = snap["symbol"].map(lambda s: wf_trend.get(str(s), {}).get("max_dd", 0.0))
    snap["wf_trend_monthly_pnl"] = snap["symbol"].map(lambda s: wf_trend.get(str(s), {}).get("monthly_pnl", 0.0))

    st.dataframe(snap, use_container_width=True)

    if not snap.empty:
        st.caption("Regime map")
        mapping = {
            "RANGE": 1.0,
            "TREND": 2.0,
            "SPIKE": 3.0,
            "SUSTAINED": 4.0,
            "HIGH_VOL": 4.0,
            "UNKNOWN": 0.0,
        }
        heat = snap.copy()
        heat["regime_band"] = heat["regime"].map(mapping).fillna(0.0)
        if alt is not None:
            regime_chart = (
                alt.Chart(heat)
                .mark_rect()
                .encode(
                    x=alt.X("symbol:N", title="symbol"),
                    y=alt.value(20),
                    color=alt.Color(
                        "regime_band:Q",
                        scale=alt.Scale(
                            domain=[0, 1, 2, 3],
                            range=["#94a3b8", "#0ea5e9", "#10b981", "#ef4444"],
                        ),
                        legend=alt.Legend(title="regime band"),
                    ),
                    tooltip=["symbol:N", "regime:N", "regime_band:Q"],
                )
                .properties(height=60)
            )
            st.altair_chart(regime_chart, use_container_width=True)
        st.dataframe(heat[["symbol", "regime", "regime_band"]], use_container_width=True)

        st.caption("Entry ranking")
        rank = snap.copy()
        rank["total_entries"] = rank["range_entries"] + rank["trend_entries"]
        rank = rank.sort_values("total_entries", ascending=False)
        st.dataframe(
            rank[["symbol", "total_entries", "range_entries", "trend_entries"]],
            use_container_width=True,
        )

        st.caption("PnL/DD/Exposure")
        metrics_cols = [
            c
            for c in [
                "symbol",
                "pnl_estimate",
                "dd_pct",
                "exposure_pct",
                "vol_weighted_exposure_pct",
                "risk_contribution_pct",
                "size_scale",
            ]
            if c in snap.columns
        ]
        st.dataframe(snap[metrics_cols], use_container_width=True)

        st.caption("Volatility-weighted risk ranking")
        risk_rank = snap.copy()
        risk_rank = risk_rank.sort_values(["risk_contribution_pct", "vol_weighted_exposure_pct"], ascending=False)
        st.dataframe(
            risk_rank[
                [
                    "symbol",
                    "risk_contribution_pct",
                    "vol_weighted_exposure_pct",
                    "size_scale",
                    "dd_pct",
                ]
            ],
            use_container_width=True,
        )

        if enable_heavy:
            st.caption("Correlation matrix (1m returns)")
            ret_mat = _build_return_matrix(symbols, max_rows_per_symbol=int(corr_rows))
            if ret_mat.empty or ret_mat.shape[1] < 2:
                st.info("Not enough symbol return series for correlation matrix")
            else:
                corr = ret_mat.corr()
                if alt is not None:
                    corr_long = corr.reset_index().melt(id_vars="index", var_name="symbol_y", value_name="corr")
                    corr_long = corr_long.rename(columns={"index": "symbol_x"})
                    heatmap = (
                        alt.Chart(corr_long)
                        .mark_rect()
                        .encode(
                            x=alt.X("symbol_x:N", title="symbol"),
                            y=alt.Y("symbol_y:N", title="symbol"),
                            color=alt.Color(
                                "corr:Q",
                                scale=alt.Scale(domain=[-1, 0, 1], range=["#2563eb", "#f8fafc", "#dc2626"]),
                                legend=alt.Legend(title="corr"),
                            ),
                            tooltip=["symbol_x:N", "symbol_y:N", "corr:Q"],
                        )
                        .properties(height=260)
                    )
                    st.altair_chart(heatmap, use_container_width=True)
                st.dataframe(corr, use_container_width=True)

            st.caption("Walkforward metrics by symbol")
            wf_cols = [
                "symbol",
                "wf_range_pf",
                "wf_range_win_rate",
                "wf_range_max_dd",
                "wf_range_monthly_pnl",
                "wf_trend_pf",
                "wf_trend_win_rate",
                "wf_trend_max_dd",
                "wf_trend_monthly_pnl",
            ]
            st.dataframe(snap[wf_cols], use_container_width=True)


def _render_runtime_metrics_panel() -> None:
    st.subheader("Runtime Metrics")
    default_path = str(DATA_DIR / "validation" / "runtime_metrics.jsonl")
    path_text = st.text_input("Metrics JSONL path", value=default_path, key="runtime_metrics_path")
    latest = _read_latest_jsonl_row(Path(path_text))
    if not latest:
        st.info("No runtime metrics found. Run `python -m auto_trader.monitor --watch ...` first.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pending Orders", str(latest.get("gateway_pending_orders", "-")))
    c2.metric("Order Latency P95 (ms)", str(latest.get("order_latency_p95_ms", "-")))
    c3.metric("Risk Block Count", str(latest.get("risk_block_count", "-")))
    c4.metric("System Load(1m)", str(latest.get("system_loadavg_1m", "-")))

    runtime_trading = latest.get("runtime_trading_enabled", False)
    emergency_stop = latest.get("runtime_emergency_stop", False)
    level, messages = _runtime_health_messages(latest)
    if level == "critical":
        st.error("Health: CRITICAL")
    elif level == "warning":
        st.warning("Health: WARNING")
    else:
        st.success("Health: OK")
    for msg in messages:
        st.caption(msg)
    st.caption(f"runtime_trading_enabled={runtime_trading}, runtime_emergency_stop={emergency_stop}, " f"timestamp={latest.get('timestamp', '-')}")
    st.json(latest)


def _render_drift_panel() -> None:
    st.subheader("Feature Drift")
    drift_path = DATA_DIR / "validation" / "weekly_revalidation" / "feature_drift_report.json"
    if not drift_path.exists():
        st.info("Drift report not found")
        return
    try:
        import json

        drift = json.loads(drift_path.read_text(encoding="utf-8"))
    except Exception:
        st.warning("Failed to read drift report")
        return
    if not isinstance(drift, dict):
        st.warning("Drift report schema invalid")
        return

    status = str(drift.get("status", "unknown"))
    block = bool(drift.get("drift_trade_block", False))
    fail_ratio = _safe_float(drift.get("fail_feature_ratio", 0.0))
    missing_ratio = _safe_float(drift.get("missing_feature_ratio", 0.0))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("status", status)
    c2.metric("trade_block", str(block).lower())
    c3.metric("fail_feature_ratio", f"{fail_ratio:.3f}")
    c4.metric("missing_feature_ratio", f"{missing_ratio:.3f}")
    if status == "fail":
        st.error("Drift status is FAIL. New entries should be blocked.")
    elif status == "warn":
        st.warning("Drift status is WARN. Monitor closely.")
    else:
        st.success("Drift status is PASS.")

    if st.checkbox("Show drift feature details", value=False):
        rows = drift.get("features", [])
        if isinstance(rows, list) and rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.info("No feature-level details")


def _fragment(run_every_sec: float) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    fragment = getattr(st, "fragment", None)
    if fragment is None:

        def _identity(func: Callable[_P, _T]) -> Callable[_P, _T]:
            return func

        return _identity
    fragment_func = cast(Any, fragment(run_every=run_every_sec))
    return cast(Callable[[Callable[_P, _T]], Callable[_P, _T]], fragment_func)


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(cast(Any, value), utc=True, errors="coerce")
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    return cast(datetime, parsed.to_pydatetime())


def _age_seconds(value: object, now: datetime | None = None) -> float | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    ref = now or datetime.now(UTC)
    return max((ref - parsed).total_seconds(), 0.0)


def _format_age(value: object, now: datetime | None = None) -> str:
    age = _age_seconds(value, now=now)
    if age is None:
        return "unknown"
    if age < 60:
        return f"{age:.0f}s"
    if age < 3600:
        return f"{age / 60.0:.1f}m"
    return f"{age / 3600.0:.1f}h"


def _freshness_level(
    value: object,
    *,
    now: datetime | None = None,
    warn_sec: int = DATA_STALE_WARN_SEC,
    crit_sec: int = DATA_STALE_CRIT_SEC,
) -> str:
    age = _age_seconds(value, now=now)
    if age is None:
        return "missing"
    if age >= crit_sec:
        return "critical"
    if age >= warn_sec:
        return "warning"
    return "ok"


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
            "pf_mean": _safe_float(item.get("pf_mean", 0.0)),
            "expectancy_bps_mean": _safe_float(item.get("expectancy_bps_mean", 0.0)),
            "period_pnl_mean": _safe_float(item.get("period_pnl_mean", 0.0)),
            "max_dd_mean": _safe_float(item.get("max_dd_mean", 0.0)),
            "closed_trades_mean": _safe_float(item.get("closed_trades_mean", 0.0)),
            "candidate_score": _safe_float(item.get("candidate_score", 0.0)),
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
                "source_trade_oos_days": _safe_float(row.get("source_trade_oos_days", 0.0)),
                "weekly_trade_oos_days": _safe_float(row.get("weekly_trade_oos_days", 0.0)),
                "weekly_fold_oos_days": _safe_float(row.get("weekly_fold_oos_days", 0.0)),
                "fold_window_drift_days": _safe_float(row.get("fold_window_drift_days", 0.0)),
                "closed_trades_mean": _safe_float(row.get("closed_trades_mean", 0.0)),
                "statistical_reasons": ", ".join(str(item) for item in row.get("statistical_reasons", []) if str(item).strip())
                if isinstance(row.get("statistical_reasons", []), list)
                else "",
            }
        )
    return out


def _render_manifest_weekly_diff_section(weekly_report: Mapping[str, object] | None) -> None:
    manifest_diff_rows = _manifest_weekly_diff_rows(weekly_report)
    if not manifest_diff_rows:
        st.info("No manifest-vs-weekly diff summary is available.")
        return
    st.subheader("Manifest vs Weekly drift")
    diff_summary: dict[str, object] = {}
    if isinstance(weekly_report, Mapping):
        raw_diff_summary = weekly_report.get("manifest_weekly_diff", {})
        if isinstance(raw_diff_summary, dict):
            diff_summary = raw_diff_summary
        else:
            diff_summary = {}
    route_count = int(_safe_float(diff_summary.get("route_count", len(manifest_diff_rows))))
    metric_match_count = int(_safe_float(diff_summary.get("metric_match_count", 0)))
    metric_mismatch_count = int(_safe_float(diff_summary.get("metric_mismatch_count", 0)))
    oos_window_drift_count = int(_safe_float(diff_summary.get("oos_window_drift_count", 0)))
    summary_cols = st.columns(4)
    summary_cols[0].metric("Routes", route_count)
    summary_cols[1].metric(
        "Metric match",
        f"{metric_match_count}/{route_count or len(manifest_diff_rows)}",
    )
    summary_cols[2].metric("Metric mismatch", metric_mismatch_count)
    summary_cols[3].metric("Fold OOS drift", oos_window_drift_count)
    st.dataframe(pd.DataFrame(manifest_diff_rows), width="stretch", hide_index=True)


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
                "age": _format_age(updated_at),
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
        _route_name, key_symbol, _ = _worker_state_key_parts(str(key))
        symbol = key_symbol
        if isinstance(result, dict):
            route = result.get("route", {})
            if isinstance(route, dict):
                symbol = str(route.get("symbol", symbol)).strip() or symbol
        if symbol:
            symbols.add(symbol)
    for key in worker_state.last_processed_bars:
        _, symbol, _ = _worker_state_key_parts(str(key))
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


def _render_range_probe_candidates(candidate_report: Mapping[str, object]) -> None:
    probe_report = candidate_report.get("range_probe_candidates")
    if not isinstance(probe_report, Mapping):
        return

    st.subheader("Range probe candidates")
    probe_status = str(probe_report.get("status", "unknown"))
    probe_symbols = _candidate_frame(probe_report)
    probe_timeframes = probe_report.get("timeframe_reports", [])
    st.caption(f"probe_status={probe_status}")

    if not isinstance(probe_timeframes, list) or not probe_timeframes:
        if probe_symbols.empty:
            st.info("No range probe candidates available.")
            return
        st.dataframe(probe_symbols, width="stretch", hide_index=True)
        return

    for timeframe_report in probe_timeframes:
        if not isinstance(timeframe_report, Mapping):
            continue
        timeframe = str(timeframe_report.get("timeframe", "")).strip() or "unknown"
        frame = _candidate_frame(timeframe_report)
        core_symbols = timeframe_report.get("core_symbols", [])
        probe_symbols_list = timeframe_report.get("probe_symbols", [])
        watchlist_symbols = timeframe_report.get("watchlist_symbols", [])
        with st.expander(
            f"{timeframe} probe: core={len(core_symbols) if isinstance(core_symbols, list) else 0} "
            f"probe={len(probe_symbols_list) if isinstance(probe_symbols_list, list) else 0} "
            f"watchlist={len(watchlist_symbols) if isinstance(watchlist_symbols, list) else 0}",
            expanded=False,
        ):
            if frame.empty:
                st.info("No rows in this timeframe probe.")
            else:
                display_cols = [
                    col
                    for col in [
                        "symbol",
                        "strategy",
                        "candidate_status",
                        "pf_mean",
                        "expectancy_bps_mean",
                        "period_pnl_mean",
                        "max_dd_mean",
                    ]
                    if col in frame.columns
                ]
                st.dataframe(frame[display_cols], width="stretch", hide_index=True)
            if isinstance(core_symbols, list):
                st.caption(f"core: {', '.join(str(x) for x in core_symbols) or '-'}")
            if isinstance(probe_symbols_list, list):
                st.caption(f"probe: {', '.join(str(x) for x in probe_symbols_list) or '-'}")
            if isinstance(watchlist_symbols, list):
                st.caption(f"watchlist: {', '.join(str(x) for x in watchlist_symbols) or '-'}")


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
        _, symbol, _ = _worker_state_key_parts(str(key))
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
                "pf_mean": _safe_float(best_row.get("pf_mean", float("nan"))),
                "expectancy_bps_mean": _safe_float(best_row.get("expectancy_bps_mean", float("nan"))),
                "max_dd_mean": _safe_float(best_row.get("max_dd_mean", float("nan"))),
                "closed_trades_mean": _safe_float(best_row.get("closed_trades_mean", float("nan"))),
                "regime": snapshot["regime"],
                "regime_timeframe": snapshot["regime_timeframe"],
                "why_not_trading": _worker_status_reason(worker_row) if worker_row else "worker result unavailable",
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
        _, symbol, _ = _worker_state_key_parts(str(key))
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
            reason = _signal_gate_summary(cast(Mapping[str, object], worker_row)) if worker_row else "worker result unavailable"
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
                "pf_mean": _safe_float(row.get("pf_mean", float("nan"))),
                "expectancy_bps_mean": _safe_float(row.get("expectancy_bps_mean", float("nan"))),
                "max_dd_mean": _safe_float(row.get("max_dd_mean", float("nan"))),
                "closed_trades_mean": _safe_float(row.get("closed_trades_mean", float("nan"))),
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


def _regime_mix_label(regime_snapshot: pd.DataFrame) -> str:
    if regime_snapshot.empty or "regime" not in regime_snapshot.columns:
        return "UNKNOWN"
    regimes = [str(value) for value in regime_snapshot["regime"].tolist() if str(value)]
    if not regimes:
        return "UNKNOWN"
    unique = sorted(set(regimes))
    if len(unique) == 1:
        return unique[0]
    if "SUSTAINED" in unique or "HIGH_VOL" in unique:
        return "HIGH_VOL MIX"
    if "SPIKE" in unique:
        return "SPIKE MIX"
    if "TREND" in unique and "RANGE" in unique:
        return "MIXED"
    return "MIXED"


def _load_job_state() -> dict[str, object]:
    payload = read_json_with_recovery(JOB_STATE_PATH)
    return payload if isinstance(payload, dict) else {}


def _save_job_state(payload: dict[str, object]) -> None:
    atomic_write_json(JOB_STATE_PATH, payload)


def _tail_text(text: str, limit: int = 20) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= limit:
        return "\n".join(lines)
    return "\n".join(lines[-limit:])


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
            "stdout": _tail_text(completed.stdout),
            "stderr": _tail_text(completed.stderr),
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


def _safe_number(value: object) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return None


def _source_snapshot(
    *,
    name: str,
    path: Path,
    frame: pd.DataFrame | None = None,
    timestamp_column: str | None = None,
) -> dict[str, object]:
    file_age = "-"
    if path.exists():
        file_age = _format_age(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC))
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
        route_name, key_symbol, key_timeframe = _worker_state_key_parts(str(key))
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
        route_name, key_symbol, key_timeframe = _worker_state_key_parts(key)
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


def _worker_status_reason(row: Mapping[str, object]) -> str:
    status = str(row.get("status", ""))
    trade_status = str(row.get("trade_status", ""))
    if trade_status in {"entry", "exit", "add"}:
        return "発注済み"
    mapping = {
        "already_processed": "同一確定足を処理済み",
        "no_signal": "シグナル未成立",
        "missing_data": "マーケットデータ不足",
        "not_enabled": "対象外シンボル",
        "disabled": "シンボル無効",
        "risk_blocked": "リスク制限で停止",
        "qty_zero": "ロットが0",
        "no_action": "発注条件未成立",
    }
    return mapping.get(status, status or "unknown")


def _signal_gate_summary(row: Mapping[str, object]) -> str:
    trade_status = str(row.get("trade_status", ""))
    if trade_status in {"entry", "exit", "add"}:
        return "発注済み"
    parts: list[str] = []
    if "entry_signal" in row:
        parts.append("entry成立" if bool(row.get("entry_signal", False)) else "entry未成立")
    if "exit_signal" in row and bool(row.get("exit_signal", False)):
        parts.append("exit成立")
    if "add_signal" in row and bool(row.get("add_signal", False)):
        parts.append("add成立")
    if "pass_filter" in row and not bool(row.get("pass_filter", False)):
        parts.append("filter未通過")
    if "risk_blocked" in row and bool(row.get("risk_blocked", False)):
        parts.append("risk制限")
    reason_codes = str(row.get("reason_codes", "")).strip()
    if reason_codes:
        parts.append(reason_codes)
    if "gateway_status" in row and str(row.get("gateway_status", "")).strip():
        parts.append(str(row.get("gateway_status", "")))
    if not parts:
        return "signal snapshot unavailable"
    return "; ".join(parts)


def _candidate_rollup(candidate_report: Mapping[str, object]) -> dict[str, object]:
    core = _csv_list(candidate_report.get("core_symbols", []))
    probe = _csv_list(candidate_report.get("probe_symbols", []))
    watchlist = _csv_list(candidate_report.get("watchlist_symbols", []))
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


def _csv_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(v).strip().upper() for v in values if str(v).strip()]


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
    if _freshness_level(worker_state.updated_at) in {"warning", "critical"}:
        warnings.append(f"Worker state is {_freshness_level(worker_state.updated_at)}.")
    if latest_metrics and _freshness_level(latest_metrics.get("timestamp", "")) in {
        "warning",
        "critical",
    }:
        metrics_level = _freshness_level(latest_metrics.get("timestamp", ""))
        warnings.append(f"Runtime metrics are {metrics_level}. Start `auto-trader-monitor.service` " "or rerun `python -m auto_trader.monitor --watch`.")
    if not risk_df.empty and "timestamp" in risk_df.columns:
        ts = pd.to_datetime(risk_df.iloc[-1]["timestamp"], utc=True).to_pydatetime()
        if is_stale(ts, datetime.now(UTC), max_delay_sec=DATA_STALE_WARN_SEC):
            risk_input_age = "unknown"
            if not risk_input_df.empty and "timestamp" in risk_input_df.columns:
                risk_input_age = _format_age(risk_input_df.iloc[-1]["timestamp"], now=datetime.now(UTC))
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
        limit_fill_rate = _safe_float(limit_metrics.get("limit_fill_rate_mean", 0.0))
        limit_taker_like_rate = _safe_float(limit_metrics.get("limit_taker_like_rate_mean", 0.0))

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


def _render_status_cards(
    *,
    runtime_state: dict[str, object],
    worker_state: WorkerState,
    runtime_metrics: dict[str, object],
    risk_df: pd.DataFrame,
    risk_input_df: pd.DataFrame,
    gateway_state: dict[str, object],
) -> None:
    level, messages = _status_banner(runtime_state, worker_state, runtime_metrics, risk_df, risk_input_df)
    if level == "critical":
        st.error("Trading health: CRITICAL")
    elif level == "warning":
        st.warning("Trading health: WARNING")
    else:
        st.success("Trading health: OK")
    for msg in messages:
        st.caption(msg)

    now = datetime.now(UTC)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Trading", "ON" if runtime_state.get("trading_enabled", False) else "OFF")
    c2.metric("Emergency", "ON" if runtime_state.get("emergency_stop", False) else "OFF")
    c3.metric("Control Age", _format_age(runtime_state.get("updated_at", ""), now=now))
    c4.metric("Worker Age", _format_age(worker_state.updated_at, now=now))
    risk_age = "-"
    if not risk_df.empty and "timestamp" in risk_df.columns:
        risk_age = _format_age(risk_df.iloc[-1]["timestamp"], now=now)
    c5.metric("Risk Age", risk_age)
    api_status = "DISCONNECTED"
    if isinstance(gateway_state, dict) and gateway_state.get("updated_at"):
        api_status = "CONNECTED"
    c6.metric("API", api_status)

    st.caption(
        "control_state updates only on manual START/STOP/EMERGENCY actions; "
        "last_cycle_at="
        f"{worker_state.last_cycle_at or '-'}, "
        f"last_error={worker_state.last_error or '-'}, "
        f"last_refresh={now.isoformat()}"
    )


def _render_overview_tab(
    *,
    runtime_state: dict[str, object],
    worker_state: WorkerState,
    runtime_metrics: dict[str, object],
    risk_df: pd.DataFrame,
    risk_input_df: pd.DataFrame,
    regime_snapshot: pd.DataFrame,
    position_df: pd.DataFrame,
    gateway_state: dict[str, object],
    candidate_report: dict[str, object],
    weekly_report: Mapping[str, object] | None = None,
) -> None:
    # Render persistent status banner at the top for immediate visibility
    _render_persistent_status_banner(
        runtime_state=runtime_state,
        worker_state=worker_state,
        runtime_metrics=runtime_metrics,
        risk_df=risk_df,
    )

    _render_status_cards(
        runtime_state=runtime_state,
        worker_state=worker_state,
        runtime_metrics=runtime_metrics,
        risk_df=risk_df,
        risk_input_df=risk_input_df,
        gateway_state=gateway_state,
    )

    st.subheader("Overview")
    if runtime_metrics:
        st.info(
            "Overview shows the always-on operator view: watchlist, active trading targets, "
            "live PnL, and symbol regimes. Exposure/Risk DD come from "
            "`data/risk/risk_eval.parquet`, and API reflects the gateway state file."
        )

    live_summary = _live_pnl_summary(position_df)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Live PnL", f"{live_summary['live_unrealized_pnl']:.2f}")
    c2.metric("Live PnL %", f"{live_summary['live_unrealized_pnl_pct']:.2f}%")
    c3.metric("Exposure", _latest_value(risk_df, "portfolio_exposure_pct", "N/A"))
    c4.metric("Risk DD", _latest_value(risk_df, "current_dd_pct", "N/A"))
    c5.metric("API", "CONNECTED" if gateway_state.get("updated_at") else "DISCONNECTED")

    runtime_trading = bool(runtime_metrics.get("runtime_trading_enabled", False))
    emergency_stop = bool(runtime_metrics.get("runtime_emergency_stop", False))
    st.caption(
        f"runtime_trading_enabled={runtime_trading}, runtime_emergency_stop={emergency_stop}, "
        f"pending_orders={runtime_metrics.get('gateway_pending_orders', '-')}, "
        f"load1m={runtime_metrics.get('system_loadavg_1m', '-')}, "
        f"position_value={live_summary['position_value']:.2f}"
    )

    if not risk_df.empty and "timestamp" in risk_df.columns:
        ts = pd.to_datetime(risk_df.iloc[-1]["timestamp"], utc=True).to_pydatetime()
        now = datetime.now(UTC)
        age_seconds = (now - ts).total_seconds()

        if is_stale(ts, datetime.now(UTC), max_delay_sec=DATA_STALE_WARN_SEC):
            # Enhanced stale data warning with visual indicators
            st.error(f"🚨 RISK DATA IS STALE - Last update: {age_seconds:.1f}s ago (threshold: {DATA_STALE_WARN_SEC}s)")

            if age_seconds > DATA_STALE_CRIT_SEC:
                st.error("🔴 CRITICAL: Data is significantly stale - system may be operating on outdated information")
            else:
                st.warning("🟠 WARNING: Data is stale - verify data pipeline is functioning")
        else:
            # Fresh data indication with age information
            freshness_emoji = "🟢" if age_seconds < 15 else "🟡"
            st.success(f"{freshness_emoji} Risk data is fresh - Last update: {age_seconds:.1f}s ago")
    else:
        st.warning("🟡 Risk data unavailable - verify data pipeline")

    health_level, health_messages = _status_banner(
        runtime_state=runtime_state,
        worker_state=worker_state,
        latest_metrics=runtime_metrics,
        risk_df=risk_df,
        risk_input_df=risk_input_df,
    )
    with st.expander("Health details", expanded=health_level != "ok"):
        for message in health_messages:
            st.write(f"- {message}")

    summary = _operator_summary(
        runtime_state=runtime_state,
        worker_state=worker_state,
        latest_metrics=runtime_metrics,
        risk_df=risk_df,
        risk_input_df=risk_input_df,
        candidate_report=candidate_report,
    )
    st.subheader("Decision summary")

    # Enhanced decision summary with better visual hierarchy
    summary_container = st.container()
    with summary_container:
        # Add visual emphasis based on health level
        health_level = summary.get("health_level", "unknown")
        if health_level == "critical":
            st.markdown("🚨 **CRITICAL DECISION REQUIRED**")
        elif health_level == "warning":
            st.markdown("⚠️ **ATTENTION REQUIRED**")
        else:
            st.markdown("✅ **SYSTEM NOMINAL**")

        # Main decision metrics with larger, more prominent display
        summary_cols = st.columns(3)

        # Current state with visual indicator
        trading_state = "Trading ON" if runtime_state.get("trading_enabled", False) else "Trading OFF"
        state_emoji = "🟢" if runtime_state.get("trading_enabled", False) else "🔴"
        summary_cols[0].metric(f"{state_emoji} Current state", trading_state)

        # Route focus with context
        focus_emoji = "🎯" if summary.get("focus") else "❓"
        summary_cols[1].metric(f"{focus_emoji} Route focus", summary["focus"])

        # Next action with priority indicator
        next_action = summary["next_action"]
        action_emoji = "⚡" if health_level in ["critical", "warning"] else "🔄"
        summary_cols[2].metric(f"{action_emoji} Next action", next_action)

        # Detailed metrics in expandable section
        with st.expander("📊 Detailed decision metrics", expanded=False):
            st.caption(
                f"health={summary['health_level']}, decision={summary['decision_status']}, "
                f"limit_fill_rate={summary['limit_fill_rate']:.3f}, "
                f"limit_taker_like_rate={summary['limit_taker_like_rate']:.3f}"
            )

            # Display reasons with better formatting
            if summary["reasons"]:
                st.markdown("**Decision reasons:**")
                for reason in summary["reasons"]:
                    st.markdown(f"• {reason}")
            else:
                st.info("No specific reasons recorded")

    st.subheader("Runtime snapshot")
    snapshot = pd.DataFrame(
        [
            {
                "runtime_trading_enabled": runtime_state.get("trading_enabled", False),
                "runtime_emergency_stop": runtime_state.get("emergency_stop", False),
                "close_all_requested": runtime_state.get("close_all_requested", False),
                "runtime_updated_at": runtime_state.get("updated_at", ""),
                "worker_updated_at": worker_state.updated_at,
                "worker_last_cycle_at": worker_state.last_cycle_at,
                "worker_last_error": worker_state.last_error,
            }
        ]
    )
    st.dataframe(snapshot, width="stretch")

    st.subheader("Live PnL")
    live_pnl_frame = _live_pnl_frame(position_df)
    if live_pnl_frame.empty:
        st.info("No open positions yet.")
    else:
        live_pnl_cols = [
            col
            for col in [
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
            if col in live_pnl_frame.columns
        ]
        st.dataframe(live_pnl_frame[live_pnl_cols], width="stretch", hide_index=True)

    _render_exchange_position_sync(position_df)

    candidate_rows = _candidate_frame(candidate_report)
    candidate_watchlist = _candidate_frame(candidate_report, "watchlist")
    best_rows = candidate_report.get("best_by_symbol_strategy", [])
    candidate_status_map: dict[str, str] = {}
    if isinstance(best_rows, list):
        for row in best_rows:
            if isinstance(row, dict):
                row_map = cast(dict[str, object], row)
                candidate_status_map[str(row_map.get("symbol", ""))] = str(row_map.get("candidate_status", ""))
    active_symbols = _active_worker_symbols(worker_state)
    candidate_rows_raw = candidate_report.get("rows", [])
    candidate_symbols_set: set[str] = set()
    if isinstance(candidate_rows_raw, list):
        for row in candidate_rows_raw:
            if isinstance(row, dict):
                row_map = cast(dict[str, object], row)
                symbol = str(row_map.get("symbol", ""))
                if symbol:
                    candidate_symbols_set.add(symbol)
    candidate_symbols = sorted(candidate_symbols_set)
    watchlist_symbols = (
        sorted(candidate_watchlist["symbol"].astype(str).unique().tolist()) if not candidate_watchlist.empty and "symbol" in candidate_watchlist.columns else []
    )
    regime_symbols = sorted(set(active_symbols) | set(candidate_symbols))
    show_core = st.checkbox("Show core", value=True, key="overview_symbols_show_core")
    show_watchlist = st.checkbox("Show watchlist", value=False, key="overview_symbols_show_watchlist")
    show_probe = st.checkbox("Show probe", value=False, key="overview_symbols_show_probe")
    status_filter: set[str] = set()
    if show_core:
        status_filter.add("core")
    if show_watchlist:
        status_filter.add("watchlist")
    if show_probe:
        status_filter.add("probe")

    def _filter_status(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        if not status_filter:
            return frame.iloc[0:0].copy()
        return frame[frame["candidate_status"].isin(status_filter)].copy()

    def _render_strategy_table(strategy: str, title: str) -> None:
        table = _strategy_symbol_table(
            candidate_rows=candidate_rows,
            strategy=strategy,
            worker_state=worker_state,
            risk_df=risk_df,
            candidate_status_map=candidate_status_map,
            active_symbols=set(active_symbols),
            watchlist_symbols=set(watchlist_symbols),
        )
        table = _filter_status(table)
        st.subheader(title)
        if table.empty:
            st.info("No symbol rows match the current candidate-status filters.")
            return
        display_cols = [
            col
            for col in [
                "symbol",
                "route",
                "candidate_status",
                "strategy",
                "timeframe",
                "pf_mean",
                "expectancy_bps_mean",
                "max_dd_mean",
                "closed_trades_mean",
                "regime",
                "regime_timeframe",
                "why_not_trading",
                "risk_blocked",
                "entry_signal",
                "pass_filter",
                "last_processed_bar",
                "exposure_pct",
                "dd_pct",
                "size_scale",
                "cycle_state",
                "trade_status",
            ]
            if col in table.columns
        ]
        st.dataframe(table[display_cols], width="stretch", hide_index=True)

    _render_strategy_table("trend", "Trend performance")
    _render_strategy_table("range", "Range performance")

    limit_frame = _limit_evidence_frame(candidate_report)
    st.subheader("Limit evidence")
    if limit_frame.empty:
        st.info("No limit evidence available in the current candidate report.")
    else:
        st.dataframe(limit_frame, width="stretch", hide_index=True)
    _render_range_probe_candidates(candidate_report)

    st.subheader("Regime by symbol")
    if not regime_symbols:
        st.info("No symbols available for regime view.")
    else:
        regime_view = regime_snapshot[regime_snapshot["symbol"].isin(regime_symbols)].copy()
        if regime_view.empty:
            st.info("No regime parquet files found for watchlist or active symbols.")
        else:
            show_active = st.checkbox("Show active", value=True, key="regime_show_active")
            show_watchlist = st.checkbox("Show watchlist", value=False, key="regime_show_watchlist")
            purpose_rows = []
            active_set = set(active_symbols)
            watchlist_set = set(watchlist_symbols)
            for _, row in regime_view.iterrows():
                symbol = str(row.get("symbol", ""))
                if symbol in active_set and symbol in watchlist_set:
                    purpose = "active+watchlist"
                elif symbol in active_set:
                    purpose = "active"
                elif symbol in watchlist_set:
                    purpose = "watchlist"
                else:
                    purpose = "candidate"
                purpose_rows.append({**cast(dict[str, object], row.to_dict()), "purpose": purpose})
            regime_display = pd.DataFrame(purpose_rows)
            enabled_purposes = {
                purpose
                for purpose, enabled in (
                    ("active", show_active),
                    ("active+watchlist", show_active or show_watchlist),
                    ("watchlist", show_watchlist),
                    ("candidate", False),
                )
                if enabled
            }
            if enabled_purposes:
                regime_display = regime_display[regime_display["purpose"].isin(enabled_purposes)].copy()
            else:
                regime_display = regime_display.iloc[0:0].copy()
            loaded_symbols = set(regime_view["symbol"].astype(str))
            regime_display = regime_display[["symbol", "timeframe", "purpose", "regime", "age", "updated_at"]].copy()
            if regime_display.empty:
                st.info("No regime rows match the current filters.")
            else:
                st.dataframe(regime_display, width="stretch", hide_index=True)
            missing = sorted(set(regime_symbols) - loaded_symbols)
            if missing:
                st.warning(f"Missing regime files for: {', '.join(missing)}")

    st.subheader("Data sources")
    runtime_env_path = DATA_DIR / "validation" / "weekly_autotune" / "route_selection_runtime.env"
    runtime_route_path = _route_selection_path()
    weekly_report_path = _weekly_revalidation_report_path()
    source_rows = [
        _source_snapshot(
            name="runtime_state",
            path=DATA_DIR / "runtime" / "control_state.json",
            timestamp_column=None,
        ),
        _source_snapshot(
            name="worker_state",
            path=DATA_DIR / "runtime" / "worker_state.json",
            timestamp_column=None,
        ),
        _source_snapshot(
            name="positions",
            path=DATA_DIR / "positions" / "positions.parquet",
            frame=position_df,
            timestamp_column="updated_at" if "updated_at" in position_df.columns else None,
        ),
        _source_snapshot(
            name="runtime_metrics",
            path=DEFAULT_RUNTIME_METRICS_PATH,
            timestamp_column=None,
        ),
        _source_snapshot(
            name="risk_eval",
            path=DATA_DIR / "risk" / "risk_eval.parquet",
            frame=risk_df,
            timestamp_column="timestamp" if "timestamp" in risk_df.columns else None,
        ),
        _source_snapshot(
            name="risk_input",
            path=DATA_DIR / "risk" / "risk_input.parquet",
            frame=risk_input_df,
            timestamp_column="timestamp" if "timestamp" in risk_input_df.columns else None,
        ),
        _source_snapshot(
            name="route_selection_runtime_env",
            path=runtime_env_path,
            timestamp_column=None,
        ),
        _source_snapshot(
            name="weekly_revalidation_report",
            path=weekly_report_path,
            timestamp_column=None,
        ),
        _source_snapshot(
            name="runtime_route_selection",
            path=runtime_route_path,
            timestamp_column=None,
        ),
    ]
    st.dataframe(pd.DataFrame(source_rows), width="stretch")


def _render_trading_tab(
    *,
    worker_state: WorkerState,
    position_df: pd.DataFrame,
    risk_df: pd.DataFrame,
    candidate_report: dict[str, object],
) -> None:
    st.subheader("Trading")
    st.caption("Trading focuses on live routes, worker state, and block reasons. " "Overview carries the heavier portfolio and risk snapshot.")
    summary = _operator_summary(
        runtime_state=_load_runtime_state(),
        worker_state=worker_state,
        latest_metrics=_load_runtime_metrics(DEFAULT_RUNTIME_METRICS_PATH),
        risk_df=risk_df,
        risk_input_df=_read_optional(DATA_DIR / "risk" / "risk_input.parquet"),
        candidate_report=candidate_report,
    )
    summary_cols = st.columns(3)
    summary_cols[0].metric("Route focus", summary["focus"])
    summary_cols[1].metric("Decision", summary["decision_status"])
    summary_cols[2].metric("Next action", summary["next_action"])
    st.caption(
        f"health={summary['health_level']}, limit_fill_rate={summary['limit_fill_rate']:.3f}, " f"limit_taker_like_rate={summary['limit_taker_like_rate']:.3f}"
    )
    for reason in summary["reasons"]:
        st.caption(f"- {reason}")

    worker_frame = _worker_last_results_frame(worker_state)
    if worker_frame.empty:
        st.info("⏳ No worker results yet. Waiting for the worker to complete and persist at least one cycle.")
    else:
        worker_frame["why_not_trading"] = worker_frame.apply(lambda row: _worker_status_reason(row.to_dict()), axis=1)

        # Add visual status indicators
        def _get_status_emoji(status: str) -> str:
            status_lower = str(status).lower()
            if "active" in status_lower or "trading" in status_lower:
                return "🟢"
            elif "blocked" in status_lower or "error" in status_lower:
                return "🔴"
            elif "warning" in status_lower or "pending" in status_lower:
                return "🟡"
            else:
                return "⚪"

        # Add emoji indicators for key columns
        if "status" in worker_frame.columns:
            worker_frame = worker_frame.copy()
            worker_frame["status_display"] = worker_frame["status"].apply(lambda x: f"{_get_status_emoji(x)} {x}")

        if "risk_blocked" in worker_frame.columns:
            worker_frame["risk_blocked_display"] = worker_frame["risk_blocked"].apply(lambda x: "🚫 BLOCKED" if x else "✅ CLEAR")

        cols = [
            "symbol",
            "status_display" if "status_display" in worker_frame.columns else "status",
            "why_not_trading",
            "trade_status",
            "gateway_status",
            "gateway_reason",
            "risk_blocked_display" if "risk_blocked_display" in worker_frame.columns else "risk_blocked",
            "entry_signal",
            "exit_signal",
            "add_signal",
            "pass_filter",
            "reason_codes",
        ]
        available = [col for col in cols if col in worker_frame.columns]

        # Display with better formatting
        st.dataframe(
            worker_frame[available],
            use_container_width=True,
            hide_index=True,
        )

        # Add summary statistics
        total_routes = len(worker_frame)
        blocked_count = len(worker_frame[worker_frame.get("risk_blocked", False)])
        active_count = total_routes - blocked_count

        st.caption(f"📊 Route summary: {active_count} active / {blocked_count} blocked / {total_routes} total")

    st.subheader("Live trade routes")
    route_frame = _worker_trade_routes_frame(worker_state)
    if route_frame.empty:
        route_frame = _candidate_trade_routes_frame(candidate_report)
        if not route_frame.empty:
            st.caption("📋 Worker cycle results are not available yet. Showing configured live routes from the current route-selection manifest.")
    if route_frame.empty:
        st.info("⏳ No live trade routes yet.")
    else:
        # Add visual indicators for route types
        def _get_route_type_emoji(status: str) -> str:
            status_lower = str(status).lower()
            if "primary" in status_lower or "core" in status_lower:
                return "⭐"
            elif "shadow" in status_lower or "backup" in status_lower:
                return "🔄"
            elif "probe" in status_lower:
                return "🔍"
            else:
                return "📊"

        if "candidate_status" in route_frame.columns:
            route_frame = route_frame.copy()
            route_frame["route_type_display"] = route_frame["candidate_status"].apply(lambda x: f"{_get_route_type_emoji(x)} {x}")

        # Add status indicators
        if "risk_blocked" in route_frame.columns:
            route_frame["blocking_status"] = route_frame["risk_blocked"].apply(lambda x: "🚫" if x else "✅")

        route_cols = [
            col
            for col in [
                "symbol",
                "strategy",
                "timeframe",
                "route_type_display" if "route_type_display" in route_frame.columns else "candidate_status",
                "expected_regime",
                "status",
                "trade_status",
                "signal_regime",
                "entry_signal",
                "exit_signal",
                "blocking_status" if "blocking_status" in route_frame.columns else "risk_blocked",
            ]
            if col in route_frame.columns
        ]

        st.dataframe(
            route_frame[route_cols],
            use_container_width=True,
            hide_index=True,
        )

        # Add route type summary
        if "candidate_status" in route_frame.columns:
            status_counts = route_frame["candidate_status"].value_counts()
            summary_text = " | ".join([f"{count} {status}" for status, count in status_counts.items()])
            st.caption(f"📊 Route composition: {summary_text}")

    st.subheader("Last processed bars")
    if not worker_state.last_processed_bars:
        st.info("No processed bars yet.")
        return
    rows = []
    for key, ts in sorted(worker_state.last_processed_bars.items()):
        route, symbol, timeframe = _worker_state_key_parts(key)
        rows.append(
            {
                "route": route,
                "symbol": symbol,
                "timeframe": timeframe or "-",
                "last_processed_bar": ts,
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True)


def _render_charts_tab(
    *,
    risk_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
    candidate_report: Mapping[str, object],
) -> None:
    st.subheader("Charts")
    st.caption(
        "Purpose: decide whether this symbol is tradable now. The main chart emphasizes "
        "price action, regime, signal timing, and risk blocks; everything else is secondary."
    )
    overlay_enabled = st.checkbox("Enable chart overlay", value=False, key="charts_overlay_enabled")
    if not overlay_enabled:
        st.caption("Enable the overlay to render symbol charts.")
        return

    core_rows = _core_symbol_focus_rows(candidate_report)
    if not core_rows:
        st.info("No core symbols are available in the current candidate report.")
        return

    summary_frame = pd.DataFrame(core_rows)
    display_cols = [
        col
        for col in [
            "symbol",
            "timeframe",
            "strategy",
            "candidate_status",
            "candidate_score",
            "pf_mean",
            "expectancy_bps_mean",
            "monthly_pnl_mean",
            "max_dd_mean",
        ]
        if col in summary_frame.columns
    ]
    style_frame = summary_frame[display_cols].copy()
    color_map = {
        "core": "#0f5132",
        "probe": "#664d03",
        "watchlist": "#1f2937",
    }
    if "candidate_status" in style_frame.columns:
        style_frame = cast(Any, style_frame.style).map(
            lambda v: f"background-color: {color_map.get(str(v), '#1f2937')}; color: white;",
            subset=["candidate_status"],
        )
    st.dataframe(style_frame, use_container_width=True, hide_index=True)
    st.caption("Core-only selection. Timeframe and strategy are resolved from the candidate report.")

    core_symbol_options = [str(row["symbol"]) for row in core_rows]
    overlay_symbol = st.selectbox(
        "Core Symbol",
        options=core_symbol_options,
        index=0,
        key="charts_overlay_symbol",
    )
    selected_row = next((row for row in core_rows if str(row.get("symbol", "")) == overlay_symbol), core_rows[0])
    overlay_timeframe = str(selected_row.get("timeframe", "1m")).strip() or "1m"
    overlay_strategy = str(selected_row.get("strategy", "trend")).strip() or "trend"
    st.caption(f"Selected core setup: symbol={overlay_symbol}, timeframe={overlay_timeframe}, " f"strategy={overlay_strategy}")

    regime_df = _read_optional(DATA_DIR / "regime" / f"{overlay_symbol}_{overlay_timeframe}_regime.parquet")
    signal_df = _read_optional(DATA_DIR / "signals" / f"{overlay_symbol}_{overlay_timeframe}_{overlay_strategy}_signals.parquet")
    overlay_fast_mode = st.checkbox("Compact mode", value=True, key="charts_overlay_fast_mode")
    max_rows_default = 180 if overlay_fast_mode else 360
    max_rows_limit = 600 if overlay_fast_mode else 1500
    max_rows = st.slider(
        "Chart window bars",
        min_value=100,
        max_value=max_rows_limit,
        value=max_rows_default,
        step=100,
        key="charts_overlay_bars",
    )
    symbol_ohlcv = _read_optional(DATA_DIR / "parquet" / f"{overlay_symbol}_{overlay_timeframe}.parquet")
    overlay = build_overlay_frame(
        ohlcv_df=symbol_ohlcv if not symbol_ohlcv.empty else ohlcv_df,
        signal_df=signal_df,
        regime_df=regime_df,
        risk_df=risk_df,
        max_rows=max_rows,
    )
    if overlay.empty:
        st.info("Overlay data unavailable")
        return
    overlay["timestamp"] = pd.to_datetime(overlay["timestamp"], utc=True)
    latest = overlay.iloc[-1]
    summary_cols = st.columns(5)
    summary_cols[0].metric("Symbol", overlay_symbol)
    summary_cols[1].metric("TF", overlay_timeframe)
    summary_cols[2].metric("Close", f"{float(latest.get('close', 0.0)):.4f}")
    summary_cols[3].metric("Regime", str(latest.get("regime", "UNKNOWN")))
    summary_cols[4].metric(
        "Risk Blocked",
        "YES" if bool(latest.get("risk_blocked", False)) else "NO",
    )
    decision_bits: list[str] = []
    if bool(latest.get("entry_signal", False)):
        decision_bits.append("entry")
    if bool(latest.get("exit_signal", False)):
        decision_bits.append("exit")
    if bool(latest.get("risk_blocked", False)):
        decision_bits.append("risk-blocked")
    if not decision_bits:
        decision_bits.append("no active signal")
    st.caption(f"Decision focus: {', '.join(decision_bits)}")
    overlay_view = overlay.copy()
    if overlay_fast_mode:
        overlay_view = _downsample_for_chart(overlay_view, max_points=300)

    left, right = st.columns([4, 1])
    with left:
        st.subheader("Price action")
        st.caption("Candles, entries, exits, risk blocks, and regime background. Read this first.")
        _render_candlestick_overlay(overlay_view)
    with right:
        st.subheader("ML score")
        if {"timestamp", "ml_score"}.issubset(overlay_view.columns):
            ml_frame = overlay_view.copy()
            ml_frame["timestamp"] = pd.to_datetime(ml_frame["timestamp"], utc=True)
            ml_chart = (
                alt.Chart(ml_frame)
                .mark_line(color="#0f766e", strokeWidth=2)
                .encode(
                    x=alt.X("timestamp:T", title="timestamp"),
                    y=alt.Y("ml_score:Q", title="ML score"),
                    tooltip=["timestamp:T", "ml_score:Q", "ml_score_source:N"],
                )
                .properties(height=280)
                .interactive(bind_x=True, bind_y=True)
            )
            st.altair_chart(ml_chart, use_container_width=True)
            latest_ml = float(pd.to_numeric(ml_frame["ml_score"], errors="coerce").fillna(0.0).iloc[-1])
            source = str(ml_frame.iloc[-1].get("ml_score_source", "position_size_ratio"))
            st.caption(f"latest={latest_ml:.3f}, source={source}")
        else:
            st.info("Signal view unavailable")


def _render_analysis_tab(*, portfolio_df: pd.DataFrame, backtest_runs: list[dict[str, object]]) -> None:
    st.subheader("Analysis")
    st.caption("Heavy analysis is opt-in to keep the live console fast.")
    st.subheader("Backtest Snapshot")
    selected_run = None
    if backtest_runs:
        run_labels = [str(run["label"]) for run in backtest_runs]
        selected_label = st.selectbox(
            "Backtest run",
            options=run_labels,
            index=0,
            key="analysis_backtest_run",
        )
        selected_run = next((run for run in backtest_runs if str(run["label"]) == selected_label), None)
        if selected_run is not None:
            portfolio_df = _read_optional(Path(str(selected_run["portfolio_path"])))
            st.caption(
                "Selected run: "
                f"symbol={selected_run.get('symbol', 'UNKNOWN')}, "
                f"timeframe={selected_run.get('timeframe', 'unknown')}, "
                f"strategy={selected_run.get('strategy', 'unknown')}, "
                f"output_dir={selected_run.get('output_dir', '-')}"
            )
    if portfolio_df.empty:
        st.info("No backtest portfolio artifact found. Run `python -m auto_trader.backtest ...` first.")
    else:
        bt_c1, bt_c2, bt_c3, bt_c4 = st.columns(4)
        latest_equity = float(portfolio_df.iloc[-1]["equity"]) if "equity" in portfolio_df.columns else 0.0
        first_equity = float(portfolio_df.iloc[0]["equity"]) if "equity" in portfolio_df.columns else 0.0
        backtest_pnl = latest_equity - first_equity
        backtest_dd = float(portfolio_df["drawdown"].max()) * 100.0 if "drawdown" in portfolio_df.columns else 0.0
        bt_c1.metric("Backtest PnL", f"{backtest_pnl:.2f}")
        bt_c2.metric("Backtest MaxDD", f"{backtest_dd:.2f}%")
        bt_c3.metric("Backtest End Equity", f"{latest_equity:.2f}")
        bt_c4.metric("Rows", str(len(portfolio_df)))
        if {"timestamp", "equity"}.issubset(portfolio_df.columns):
            chart_df = portfolio_df.copy()
            chart_df["timestamp"] = pd.to_datetime(chart_df["timestamp"], utc=True)
            st.line_chart(chart_df.set_index("timestamp")[["equity"]])
        with st.expander("Backtest portfolio rows", expanded=False):
            st.dataframe(portfolio_df.tail(200), use_container_width=True)

    show_multi_symbol_panel = st.checkbox(
        "Enable Multi-Symbol Panel",
        value=False,
        key="analysis_enable_multi_symbol_panel",
    )
    show_walkforward = st.checkbox(
        "Show Walkforward Visual Check",
        value=False,
        key="analysis_show_walkforward",
    )

    if show_multi_symbol_panel:
        symbols_raw = st.text_input(
            "Symbols (comma separated)",
            value=",".join(_preferred_symbol_choices(limit=12)),
            key="analysis_symbols_input",
        )
        max_symbols = st.slider(
            "Max symbols to render",
            min_value=2,
            max_value=20,
            value=8,
            step=1,
            key="analysis_max_symbols",
        )
        enable_heavy = st.checkbox(
            "Enable heavy visualizations (correlation/walkforward tables)",
            value=False,
            key="analysis_enable_heavy",
        )
        corr_rows = st.slider(
            "Rows per symbol for correlation",
            min_value=300,
            max_value=5000,
            value=1500,
            step=100,
            key="analysis_corr_rows",
        )
        symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
        symbols = symbols[:max_symbols]
        if not symbols:
            st.info("No symbols configured")
        else:
            wf_range = _load_walkforward_metric_map("range", symbols, timeframe="1m")
            wf_trend = _load_walkforward_metric_map("trend", symbols, timeframe="1m")
            risk_df = _read_optional(DATA_DIR / "risk" / "risk_eval.parquet")
            rows = [_symbol_snapshot(s, risk_df, wf_range, wf_trend) for s in symbols]
            snap = pd.DataFrame(rows)
            snap["wf_range_pf"] = snap["symbol"].map(lambda s: wf_range.get(str(s), {}).get("pf", 0.0))
            snap["wf_range_win_rate"] = snap["symbol"].map(lambda s: wf_range.get(str(s), {}).get("win_rate", 0.0))
            snap["wf_range_max_dd"] = snap["symbol"].map(lambda s: wf_range.get(str(s), {}).get("max_dd", 0.0))
            snap["wf_range_monthly_pnl"] = snap["symbol"].map(lambda s: wf_range.get(str(s), {}).get("monthly_pnl", 0.0))
            snap["wf_trend_pf"] = snap["symbol"].map(lambda s: wf_trend.get(str(s), {}).get("pf", 0.0))
            snap["wf_trend_win_rate"] = snap["symbol"].map(lambda s: wf_trend.get(str(s), {}).get("win_rate", 0.0))
            snap["wf_trend_max_dd"] = snap["symbol"].map(lambda s: wf_trend.get(str(s), {}).get("max_dd", 0.0))
            snap["wf_trend_monthly_pnl"] = snap["symbol"].map(lambda s: wf_trend.get(str(s), {}).get("monthly_pnl", 0.0))
            st.dataframe(snap, use_container_width=True)

            if not snap.empty:
                st.caption("Regime map")
                mapping = {
                    "RANGE": 1.0,
                    "TREND": 2.0,
                    "SPIKE": 3.0,
                    "SUSTAINED": 4.0,
                    "HIGH_VOL": 4.0,
                    "UNKNOWN": 0.0,
                }
                heat = snap.copy()
                heat["regime_band"] = heat["regime"].map(mapping).fillna(0.0)
                if alt is not None:
                    regime_chart = (
                        alt.Chart(heat)
                        .mark_rect()
                        .encode(
                            x=alt.X("symbol:N", title="symbol"),
                            y=alt.value(20),
                            color=alt.Color(
                                "regime_band:Q",
                                scale=alt.Scale(
                                    domain=[0, 1, 2, 3],
                                    range=["#94a3b8", "#0ea5e9", "#10b981", "#ef4444"],
                                ),
                                legend=alt.Legend(title="regime band"),
                            ),
                            tooltip=["symbol:N", "regime:N", "regime_band:Q"],
                        )
                        .properties(height=60)
                    )
                    st.altair_chart(regime_chart, use_container_width=True)
                st.dataframe(heat[["symbol", "regime", "regime_band"]], use_container_width=True)

                st.caption("Entry ranking")
                rank = snap.copy()
                rank["total_entries"] = rank["range_entries"] + rank["trend_entries"]
                rank = rank.sort_values("total_entries", ascending=False)
                st.dataframe(
                    rank[["symbol", "total_entries", "range_entries", "trend_entries"]],
                    use_container_width=True,
                )

                st.caption("PnL/DD/Exposure")
                metrics_cols = [
                    c
                    for c in [
                        "symbol",
                        "pnl_estimate",
                        "dd_pct",
                        "exposure_pct",
                        "vol_weighted_exposure_pct",
                        "risk_contribution_pct",
                        "size_scale",
                    ]
                    if c in snap.columns
                ]
                st.dataframe(snap[metrics_cols], use_container_width=True)

                st.caption("Volatility-weighted risk ranking")
                risk_rank = snap.copy()
                risk_rank = risk_rank.sort_values(["risk_contribution_pct", "vol_weighted_exposure_pct"], ascending=False)
                st.dataframe(
                    risk_rank[
                        [
                            "symbol",
                            "risk_contribution_pct",
                            "vol_weighted_exposure_pct",
                            "size_scale",
                            "dd_pct",
                        ]
                    ],
                    use_container_width=True,
                )

                if enable_heavy:
                    st.caption("Correlation matrix (1m returns)")
                    ret_mat = _build_return_matrix(symbols, max_rows_per_symbol=int(corr_rows))
                    if ret_mat.empty or ret_mat.shape[1] < 2:
                        st.info("Not enough symbol return series for correlation matrix")
                    else:
                        corr = ret_mat.corr()
                        if alt is not None:
                            corr_long = corr.reset_index().melt(id_vars="index", var_name="symbol_y", value_name="corr")
                            corr_long = corr_long.rename(columns={"index": "symbol_x"})
                            heatmap = (
                                alt.Chart(corr_long)
                                .mark_rect()
                                .encode(
                                    x=alt.X("symbol_x:N", title="symbol"),
                                    y=alt.Y("symbol_y:N", title="symbol"),
                                    color=alt.Color(
                                        "corr:Q",
                                        scale=alt.Scale(
                                            domain=[-1, 0, 1],
                                            range=["#2563eb", "#f8fafc", "#dc2626"],
                                        ),
                                        legend=alt.Legend(title="corr"),
                                    ),
                                    tooltip=["symbol_x:N", "symbol_y:N", "corr:Q"],
                                )
                                .properties(height=260)
                            )
                            st.altair_chart(heatmap, use_container_width=True)
                        st.dataframe(corr, use_container_width=True)

                    st.caption("Walkforward metrics by symbol")
                    wf_cols = [
                        "symbol",
                        "wf_range_pf",
                        "wf_range_win_rate",
                        "wf_range_max_dd",
                        "wf_range_monthly_pnl",
                        "wf_trend_pf",
                        "wf_trend_win_rate",
                        "wf_trend_max_dd",
                        "wf_trend_monthly_pnl",
                    ]
                    st.dataframe(snap[wf_cols], use_container_width=True)
    else:
        st.info("Multi-symbol panel is disabled")

    if show_walkforward:
        strategy = st.selectbox(
            "Strategy",
            options=["range", "trend"],
            index=0,
            key="analysis_wf_strategy",
        )
        wf_symbol = st.selectbox(
            "WF Symbol",
            options=_discover_available_symbols(),
            index=0,
            key="analysis_wf_symbol",
        )
        wf_summary = _load_walkforward_artifact(wf_symbol, "1m", strategy, "summary")

        if wf_summary.empty:
            st.info("No walkforward report found. Run `python -m auto_trader.analysis ...` first.")
        else:
            st.caption("Fold summary: PF/WinRate/DD/PnL and invalid regime entries")
            st.dataframe(wf_summary, use_container_width=True)
            wf_fast_mode = st.checkbox("Walkforward Fast Mode", value=True, key="analysis_wf_fast_mode")
            show_wf_details = st.checkbox("Show Walkforward Details", value=False, key="analysis_wf_details")
            if show_wf_details:
                max_portfolio_rows = st.slider(
                    "WF Portfolio Rows",
                    min_value=200,
                    max_value=5000,
                    value=1000,
                    step=100,
                    key="analysis_wf_portfolio_rows",
                )
                max_trade_rows = st.slider(
                    "WF Trade Rows",
                    min_value=50,
                    max_value=2000,
                    value=300,
                    step=50,
                    key="analysis_wf_trade_rows",
                )

                wf_portfolio = _load_walkforward_artifact(wf_symbol, "1m", strategy, "portfolio")
                wf_trades = _load_walkforward_artifact(wf_symbol, "1m", strategy, "trades")
                wf_regime = _load_walkforward_artifact(wf_symbol, "1m", strategy, "regime_counts")

                if not wf_portfolio.empty:
                    st.caption("Portfolio")
                    st.dataframe(wf_portfolio.tail(max_portfolio_rows), use_container_width=True)
                if not wf_trades.empty:
                    st.caption("Trades")
                    st.dataframe(wf_trades.tail(max_trade_rows), use_container_width=True)
                if not wf_regime.empty:
                    st.caption("Regime counts")
                    st.dataframe(wf_regime, use_container_width=True)
                if wf_fast_mode:
                    st.caption("Fast mode enabled: portfolio/trade tables are truncated.")
    else:
        st.info("Walkforward visual check is disabled")


def _render_live_logs_tab(*, runtime_metrics_path: Path) -> None:
    st.subheader("Live Logs")
    metrics_path_text = st.text_input(
        "Metrics JSONL path",
        value=str(runtime_metrics_path),
        key="live_logs_runtime_metrics_path",
    )
    latest_metrics = _read_latest_jsonl_row(Path(metrics_path_text))
    if not latest_metrics:
        st.info("No runtime metrics found. Run `python -m auto_trader.monitor --watch ...` first.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Pending Orders", str(latest_metrics.get("gateway_pending_orders", "-")))
        c2.metric("Order Latency P95 (ms)", str(latest_metrics.get("order_latency_p95_ms", "-")))
        c3.metric("Risk Block Count", str(latest_metrics.get("risk_block_count", "-")))
        c4.metric("System Load(1m)", str(latest_metrics.get("system_loadavg_1m", "-")))
        runtime_trading = latest_metrics.get("runtime_trading_enabled", False)
        emergency_stop = latest_metrics.get("runtime_emergency_stop", False)
        level, messages = _runtime_health_messages(latest_metrics)
        if level == "critical":
            st.error("Health: CRITICAL")
        elif level == "warning":
            st.warning("Health: WARNING")
        else:
            st.success("Health: OK")
        for msg in messages:
            st.caption(msg)
        st.caption(f"runtime_trading_enabled={runtime_trading}, runtime_emergency_stop={emergency_stop}, " f"timestamp={latest_metrics.get('timestamp', '-')}")
        st.json(latest_metrics)

    st.subheader("Execution Events")
    if CONTROL_LOG.exists():
        events = _read_jsonl_table(str(CONTROL_LOG), tail_rows=100)
        if events.empty:
            st.info("No control events yet")
        else:
            st.dataframe(events.tail(30), use_container_width=True)
    else:
        st.info("No control events yet")

    order_events_path = DATA_DIR / "exchange" / "order_events.jsonl"
    if order_events_path.exists():
        st.caption("Order events")
        order_events = _read_jsonl_table(str(order_events_path), tail_rows=100)
        if order_events.empty:
            st.info("No order events yet")
        else:
            st.dataframe(order_events.tail(30), use_container_width=True)

    st.subheader("Raw State")
    runtime_state = _load_runtime_state()
    worker_state = _load_worker_state()
    st.json(
        {
            "runtime_state": runtime_state,
            "worker_state": {
                "updated_at": worker_state.updated_at,
                "last_cycle_at": worker_state.last_cycle_at,
                "last_error": worker_state.last_error,
                "last_processed_bars_count": len(worker_state.last_processed_bars),
                "last_results_count": len(worker_state.last_results),
            },
        }
    )


def _render_audit_tab(*, weekly_report: Mapping[str, object] | None) -> None:
    st.subheader("Audit")
    st.caption("Weekly route-validation and drift comparison. Manual refresh only.")
    _render_manifest_weekly_diff_section(weekly_report)


def _render_sidebar_controls() -> None:
    st.sidebar.subheader("Controls")
    st.sidebar.caption("Fixed here for always-visible operation. Refresh JOB recomputes risk/runtime data.")
    control_cols = st.sidebar.columns(1)
    for action in ["START", "STOP", "EMERGENCY_STOP", "EMERGENCY_CANCEL", "CLOSE_ALL"]:
        if control_cols[0].button(action, type="primary" if "EMERGENCY" in action else "secondary"):
            now = datetime.now(UTC)
            append_control_event(
                CONTROL_LOG,
                ControlEvent(
                    action=action,  # type: ignore[arg-type]
                    requested_at=now,
                    applied_at=now,
                    result="accepted",
                ),
            )
            st.sidebar.success(f"{action} recorded")

    job_state = _load_job_state()
    job_running = str(job_state.get("status", "")) == "running"
    if st.sidebar.button("Run refresh JOB", disabled=job_running):
        with st.spinner("Running refresh job..."):
            result = _run_refresh_job()
        st.session_state["last_refresh_job"] = result
        st.rerun()

    if job_state:
        status = str(job_state.get("status", "unknown"))
        if status == "success":
            st.sidebar.success("JOB: success")
        elif status == "running":
            st.sidebar.info("JOB: running")
        elif status == "failed":
            st.sidebar.error("JOB: failed")
        else:
            st.sidebar.caption(f"JOB: {status}")
        if job_state.get("started_at"):
            st.sidebar.caption(f"started_at={job_state.get('started_at')}")
        if job_state.get("finished_at"):
            st.sidebar.caption(f"finished_at={job_state.get('finished_at')}")
        if job_state.get("message"):
            st.sidebar.caption(str(job_state.get("message")))
        steps_df = _format_job_state(job_state)
        if not steps_df.empty:
            st.sidebar.dataframe(steps_df, width="stretch", hide_index=True)
        stdout_tail = str(job_state.get("stdout_tail", "")).strip()
        stderr_tail = str(job_state.get("stderr_tail", "")).strip()
        if stdout_tail:
            with st.sidebar.expander("JOB stdout"):
                st.text(stdout_tail)
        if stderr_tail:
            with st.sidebar.expander("JOB stderr"):
                st.text(stderr_tail)


@_fragment(AUTO_REFRESH_SEC)
def _render_live_monitor() -> None:
    runtime_state = _load_runtime_state()
    worker_state = _load_worker_state()
    gateway_state = read_json_with_recovery(DATA_DIR / "exchange" / "gateway_state.json")
    gateway_state = gateway_state if isinstance(gateway_state, dict) else {}
    risk_df = _read_optional(DATA_DIR / "risk" / "risk_eval.parquet")
    risk_input_df = _read_optional(DATA_DIR / "risk" / "risk_input.parquet")
    position_df = _read_optional(DATA_DIR / "positions" / "positions.parquet")
    regime_snapshot = _load_regime_snapshot()
    runtime_metrics = _load_runtime_metrics(DEFAULT_RUNTIME_METRICS_PATH)
    candidate_report = _load_candidate_report()
    weekly_candidate_report = _load_weekly_candidate_report()

    overview_tab, trading_tab, live_logs_tab = st.tabs(["Overview", "Trading", "Live Logs"])
    with overview_tab:
        _render_overview_tab(
            runtime_state=runtime_state,
            worker_state=worker_state,
            runtime_metrics=runtime_metrics,
            risk_df=risk_df,
            risk_input_df=risk_input_df,
            regime_snapshot=regime_snapshot,
            position_df=position_df,
            gateway_state=gateway_state,
            candidate_report=weekly_candidate_report or candidate_report,
            weekly_report=weekly_candidate_report,
        )
    with trading_tab:
        _render_trading_tab(
            worker_state=worker_state,
            position_df=position_df,
            risk_df=risk_df,
            candidate_report=weekly_candidate_report or candidate_report,
        )
    with live_logs_tab:
        _render_live_logs_tab(runtime_metrics_path=DEFAULT_RUNTIME_METRICS_PATH)


def _render_analysis_workspace() -> None:
    risk_df = _read_optional(DATA_DIR / "risk" / "risk_eval.parquet")
    portfolio_df = _read_optional(DATA_DIR / "backtest" / "portfolio.parquet")
    ohlcv_df = _read_optional(DATA_DIR / "parquet" / "BTCUSDT_1m.parquet")
    backtest_runs = _discover_backtest_runs()
    candidate_report = _load_candidate_report()
    weekly_candidate_report = _load_weekly_candidate_report()

    st.caption("This workspace does not auto-refresh. " "Rerun manually after generating new analysis artifacts.")
    charts_tab, analysis_tab, audit_tab = st.tabs(["Charts", "Analysis", "Audit"])
    with charts_tab:
        _render_charts_tab(
            risk_df=risk_df,
            ohlcv_df=ohlcv_df,
            candidate_report=candidate_report,
        )
    with analysis_tab:
        _render_analysis_tab(portfolio_df=portfolio_df, backtest_runs=backtest_runs)
    with audit_tab:
        _render_audit_tab(weekly_report=weekly_candidate_report)


def _legacy_main() -> None:
    st.set_page_config(page_title="Auto Trader Ops Console", layout="wide")
    _inject_ui_stability_styles()
    st.title("Auto Trader Operations Dashboard")
    st.sidebar.subheader("Performance")
    show_overlay = st.sidebar.checkbox("Show Chart Overlay", value=False)
    show_walkforward = st.sidebar.checkbox("Show Walkforward Visual Check", value=False)

    risk_df = _read_optional(DATA_DIR / "risk" / "risk_eval.parquet")
    regime_df = _read_optional(DATA_DIR / "regime" / "BTCUSDT_1m_regime.parquet")
    position_df = _read_optional(DATA_DIR / "positions" / "positions.parquet")
    portfolio_df = _read_optional(DATA_DIR / "backtest" / "portfolio.parquet")
    ohlcv_df = _read_optional(DATA_DIR / "parquet" / "BTCUSDT_1m.parquet")

    latest_regime = _latest_value(regime_df, "regime", default="UNKNOWN")
    latest_emergency = bool(risk_df.iloc[-1]["emergency_state"]) if not risk_df.empty else False
    badge = emergency_badge(latest_emergency, latest_regime)
    if badge == "EMERGENCY":
        st.error("EMERGENCY STATE ACTIVE")
    elif badge in {"HIGH_VOL", "SUSTAINED"}:
        st.warning("SUSTAINED HIGH VOL DETECTED")
    elif badge == "SPIKE":
        st.warning("SPIKE DETECTED")
    else:
        st.success("NORMAL OPERATION")

    _render_controls()
    _render_multi_symbol_panel()
    _render_runtime_metrics_panel()
    _render_drift_panel()

    st.subheader("Dashboard")
    c1, c2, c3, c4, c5 = st.columns(5)
    pnl = "-"
    dd = "-"
    if not portfolio_df.empty:
        latest_eq = float(portfolio_df.iloc[-1]["equity"])
        first_eq = float(portfolio_df.iloc[0]["equity"])
        pnl = f"{latest_eq - first_eq:.2f}"
        dd = f"{float(portfolio_df['drawdown'].max()) * 100:.2f}%"
    c1.metric("PnL", pnl)
    c2.metric("Regime", latest_regime)
    c3.metric("Exposure", _latest_value(risk_df, "portfolio_exposure_pct", "-"))
    c4.metric("MaxDD", dd)
    c5.metric("API", "CONNECTED")
    st.caption(
        f"vol_weighted_exposure_pct={_latest_value(risk_df, 'vol_weighted_exposure_pct', '-')}, " f"size_scale={_latest_value(risk_df, 'size_scale', '-')}"
    )

    st.subheader("Stale Monitor")
    if not risk_df.empty and "timestamp" in risk_df.columns:
        ts = pd.to_datetime(risk_df.iloc[-1]["timestamp"], utc=True).to_pydatetime()
        stale = is_stale(ts, datetime.now(UTC), max_delay_sec=30)
        if stale:
            st.warning("Risk data is stale")
        else:
            st.info("Risk data is fresh")
    else:
        st.warning("Risk data unavailable")

    st.subheader("Positions")
    st.dataframe(position_df, use_container_width=True)

    st.subheader("Risk")
    st.dataframe(risk_df.tail(20), use_container_width=True)

    st.subheader("Execution Events")
    if CONTROL_LOG.exists():
        events = pd.read_json(CONTROL_LOG, lines=True)
        st.dataframe(events.tail(30), use_container_width=True)
    else:
        st.info("No control events yet")

    if show_overlay:
        st.subheader("Chart Overlay")
    if show_overlay and not ohlcv_df.empty:
        overlay_strategy = st.selectbox("Overlay Strategy", options=["range", "trend"], index=0, key="overlay_strategy")
        legacy_symbols = _discover_available_symbols()
        legacy_symbol = st.selectbox("Overlay Symbol", options=legacy_symbols, index=0, key="legacy_overlay_symbol")
        legacy_timeframe_options = _discover_symbol_timeframes(legacy_symbol)
        legacy_timeframe = st.selectbox(
            "Timeframe",
            options=legacy_timeframe_options,
            index=0 if "1m" in legacy_timeframe_options else 0,
            key="legacy_overlay_timeframe",
        )
        signal_df = _read_optional(DATA_DIR / "signals" / f"{legacy_symbol}_{legacy_timeframe}_{overlay_strategy}_signals.parquet")
        overlay_fast_mode = st.checkbox("Overlay Fast Mode", value=True, key="overlay_fast_mode")
        max_rows_default = 300 if overlay_fast_mode else 800
        max_rows_limit = 2000 if overlay_fast_mode else 5000
        max_rows = st.slider(
            "Overlay Bars",
            min_value=100,
            max_value=max_rows_limit,
            value=max_rows_default,
            step=100,
        )
        symbol_ohlcv = _read_optional(DATA_DIR / "parquet" / f"{legacy_symbol}_{legacy_timeframe}.parquet")
        overlay = build_overlay_frame(
            ohlcv_df=symbol_ohlcv if not symbol_ohlcv.empty else ohlcv_df,
            signal_df=signal_df,
            regime_df=_read_optional(DATA_DIR / "regime" / f"{legacy_symbol}_{legacy_timeframe}_regime.parquet"),
            risk_df=risk_df,
            max_rows=max_rows,
        )
        if overlay.empty:
            st.info("Overlay data unavailable")
        else:
            overlay["timestamp"] = pd.to_datetime(overlay["timestamp"], utc=True)
            if len(overlay) > 1:
                start_default = max(0, len(overlay) - min(300, len(overlay)))
                idx_range = st.slider(
                    "Visible Range (index)",
                    min_value=0,
                    max_value=len(overlay) - 1,
                    value=(start_default, len(overlay) - 1),
                    step=1,
                )
                overlay_view = overlay.iloc[idx_range[0] : idx_range[1] + 1].copy()
            else:
                overlay_view = overlay.copy()
            if overlay_fast_mode:
                overlay_view = _downsample_for_chart(overlay_view, max_points=800)
            _render_candlestick_overlay(overlay_view)
            if not overlay_fast_mode:
                chart = overlay_view.set_index("timestamp")
                st.line_chart(chart[["ml_score", "regime_band"]])
                st.caption("Aux overlay: ml_score + regime_band")
            else:
                st.caption("Fast mode: aux overlay chart skipped for performance")
    elif show_overlay:
        st.info("No OHLCV data available for chart")

    if show_walkforward:
        st.subheader("Walkforward Visual Check")
        strategy = st.selectbox("Strategy", options=["range", "trend"], index=0, key="wf_strategy")
        wf_symbol = st.selectbox("WF Symbol", options=_discover_available_symbols(), index=0, key="wf_symbol")
        wf_summary = _load_walkforward_artifact(wf_symbol, "1m", strategy, "summary")

        if wf_summary.empty:
            st.info("No walkforward report found. Run `python -m auto_trader.analysis ...` first.")
        else:
            st.caption("Fold summary: PF/WinRate/DD/PnL and invalid regime entries")
            st.dataframe(wf_summary, use_container_width=True)
            wf_fast_mode = st.checkbox("Walkforward Fast Mode", value=True, key="wf_fast_mode")
            show_wf_details = st.checkbox("Show Walkforward Details", value=False, key="wf_details")
            if show_wf_details:
                max_portfolio_rows = st.slider("WF Portfolio Rows", min_value=200, max_value=5000, value=1000, step=100)
                max_trade_rows = st.slider("WF Trade Rows", min_value=50, max_value=2000, value=300, step=50)

                wf_portfolio = _load_walkforward_artifact(wf_symbol, "1m", strategy, "portfolio")
                wf_trades = _load_walkforward_artifact(wf_symbol, "1m", strategy, "trades")
                wf_regime = _load_walkforward_artifact(wf_symbol, "1m", strategy, "regime_counts")
                wf_invalid = _load_walkforward_artifact(wf_symbol, "1m", strategy, "invalid_entries")

                if not wf_portfolio.empty and {"timestamp", "equity", "fold"}.issubset(wf_portfolio.columns):
                    p = wf_portfolio.tail(max_portfolio_rows).copy()
                    p["timestamp"] = pd.to_datetime(p["timestamp"], utc=True)
                    p = p.sort_values(["fold", "timestamp"])
                    if wf_fast_mode:
                        p = _downsample_for_chart(p, max_points=1000)
                    st.line_chart(p.set_index("timestamp")[["equity"]])
                if not wf_trades.empty and {"timestamp", "side", "price", "fold"}.issubset(wf_trades.columns):
                    st.caption("Trade timing/direction")
                    cols = ["timestamp", "fold", "side", "price", "size", "status"]
                    st.dataframe(wf_trades[cols].tail(max_trade_rows), use_container_width=True)
                if not wf_regime.empty:
                    st.caption("Regime distribution")
                    st.dataframe(wf_regime, use_container_width=True)
                if not wf_invalid.empty:
                    st.warning(f"Invalid regime entries detected: {len(wf_invalid)}")
                    cols = [
                        c
                        for c in [
                            "timestamp",
                            "symbol",
                            "timeframe",
                            "regime",
                            "entry_signal",
                            "pass_filter",
                        ]
                        if c in wf_invalid.columns
                    ]
                    st.dataframe(wf_invalid[cols].tail(50), use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="Auto Trader Ops Console", layout="wide")
    _inject_ui_stability_styles()
    st.title("Auto Trader Operations Dashboard")
    st.caption("Live Monitor auto-refreshes every 10 seconds. " "Analysis Workspace refreshes only on manual rerun.")
    _render_sidebar_controls()
    live_tab, analysis_tab = st.tabs(["Live Monitor", "Analysis Workspace"])
    with live_tab:
        _render_live_monitor()
    with analysis_tab:
        _render_analysis_workspace()


if __name__ == "__main__":
    main()
