"""Reusable UI component functions for the GUI module.

Small, composable rendering blocks used by the tab-level renderers in
``ui_tabs``.  Each function renders a discrete Streamlit widget or panel.
"""

from __future__ import annotations

import importlib
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

from auto_trader.gui.data_loader import (
    DATA_DIR,
    _build_return_matrix,
    _cached_exchange_positions_snapshot,
    _candidate_frame,
    _exchange_sync_cache_marker,
    _is_safe_data_path,
    _load_walkforward_metric_map,
    _position_reconciliation_frame,
    _preferred_symbol_choices,
    _read_latest_jsonl_row,
    _read_optional,
    _runtime_health_messages,
    _symbol_snapshot,
)
from auto_trader.gui.overlay import build_regime_segments
from auto_trader.gui.state import ControlEvent, append_control_event
from auto_trader.gui.utils import (
    safe_float as _safe_float,
)
from auto_trader.worker.state import WorkerState

CONTROL_LOG = DATA_DIR / "gui" / "control_events.jsonl"

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
        ("EMERGENCY_STOP", col3, "⛔ EMERGENCY STOP - This will immediately halt all trading activity"),
        ("EMERGENCY_CANCEL", col4, "🔄 EMERGENCY CANCEL - This will cancel the emergency stop state"),
        ("CLOSE_ALL", col5, "❌ CLOSE ALL - This will close all positions immediately"),
    ]

    for action, col, help_text in emergency_buttons:
        if col.button(action, type="primary", use_container_width=True, help=help_text):
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
    if not _is_safe_data_path(path_text):
        st.error("Path must be within the project data directory.")
        return
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

