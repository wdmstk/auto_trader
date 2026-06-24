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
from typing import Any

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
    _candidate_trade_routes_frame,
    _format_job_state,
    _is_safe_data_path,
    _live_pnl_frame,
    _live_pnl_summary,
    _load_job_state,
    _load_runtime_metrics,
    _load_runtime_state,
    _load_worker_state,
    _operator_summary,
    _read_jsonl_table,
    _read_latest_jsonl_row,
    _read_optional,
    _run_refresh_job,
    _runtime_health_messages,
    _status_banner,
    _worker_last_results_frame,
    _worker_trade_routes_frame,
)
from auto_trader.gui.state import ControlEvent, append_control_event, is_stale
from auto_trader.gui.ui_components import (
    CONTROL_LOG,
    _render_exchange_position_sync,
    _render_persistent_status_banner,
)
from auto_trader.gui.utils import format_age as _format_age
from auto_trader.gui.utils import latest_value as _latest_value
from auto_trader.gui.utils import worker_status_reason as _worker_status_reason
from auto_trader.worker.state import WorkerState


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
    with st.expander("Health details", expanded=False):
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

        # Detailed metrics in expandable section (collapsed by default for performance)
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
    with st.expander("Show positions", expanded=False):
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


def _render_live_logs_tab(*, runtime_metrics_path: Path) -> None:
    st.subheader("Live Logs")
    metrics_path_text = st.text_input(
        "Metrics JSONL path",
        value=str(runtime_metrics_path),
        key="live_logs_runtime_metrics_path",
    )
    if not _is_safe_data_path(metrics_path_text):
        st.error("Path must be within the project data directory.")
        return
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
