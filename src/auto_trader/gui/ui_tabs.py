"""Tab renderer and layout functions for the GUI module.

Each function renders a specific tab or layout section of the Streamlit
dashboard.  These compose UI components from ``ui_components`` and load
data via ``data_loader``.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import streamlit as st

try:
    alt: Any = importlib.import_module("altair")
except Exception:  # pragma: no cover - UI fallback
    alt = None

from auto_trader.gui.data_loader import (
    DATA_DIR,
    DATA_STALE_CRIT_SEC,
    DATA_STALE_WARN_SEC,
    DEFAULT_RUNTIME_METRICS_PATH,
    _active_worker_symbols,
    _build_return_matrix,
    _candidate_frame,
    _candidate_trade_routes_frame,
    _core_symbol_focus_rows,
    _discover_available_symbols,
    _discover_backtest_runs,
    _format_job_state,
    _limit_evidence_frame,
    _live_pnl_frame,
    _live_pnl_summary,
    _load_candidate_report,
    _load_job_state,
    _load_regime_snapshot,
    _load_runtime_metrics,
    _load_runtime_state,
    _load_walkforward_artifact,
    _load_walkforward_metric_map,
    _load_weekly_candidate_report,
    _load_worker_state,
    _manifest_weekly_diff_rows,
    _operator_summary,
    _preferred_symbol_choices,
    _read_jsonl_table,
    _read_latest_jsonl_row,
    _read_optional,
    _route_selection_path,
    _run_refresh_job,
    _runtime_health_messages,
    _source_snapshot,
    _status_banner,
    _strategy_symbol_table,
    _symbol_snapshot,
    _weekly_revalidation_report_path,
    _worker_last_results_frame,
    _worker_trade_routes_frame,
)
from auto_trader.gui.overlay import build_overlay_frame
from auto_trader.gui.state import ControlEvent, append_control_event, is_stale
from auto_trader.gui.ui_components import (
    CONTROL_LOG,
    _fragment,
    _render_candlestick_overlay,
    _render_exchange_position_sync,
    _render_persistent_status_banner,
    _render_range_probe_candidates,
)
from auto_trader.gui.utils import (
    downsample_for_chart as _downsample_for_chart,
)
from auto_trader.gui.utils import (
    format_age as _format_age,
)
from auto_trader.gui.utils import (
    latest_value as _latest_value,
)
from auto_trader.gui.utils import (
    safe_float as _safe_float,
)
from auto_trader.gui.utils import (
    worker_state_key_parts as _worker_state_key_parts,
)
from auto_trader.gui.utils import (
    worker_status_reason as _worker_status_reason,
)
from auto_trader.stateio import read_json_with_recovery
from auto_trader.worker.state import WorkerState

AUTO_REFRESH_SEC = 10.0

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

