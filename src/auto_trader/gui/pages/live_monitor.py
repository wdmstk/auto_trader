"""Live Monitor page for real-time trading operations."""

from __future__ import annotations

import time

import streamlit as st

from auto_trader.gui.data_loader import (
    DATA_DIR,
    DEFAULT_RUNTIME_METRICS_PATH,
    _load_candidate_report,
    _load_regime_snapshot,
    _load_runtime_metrics,
    _load_runtime_state,
    _load_weekly_candidate_report,
    _load_worker_state,
    _read_optional,
)
from auto_trader.gui.ui_components import (
    _inject_ui_stability_styles,
)
from auto_trader.gui.ui_tabs import (
    _render_live_logs_tab,
    _render_overview_tab,
    _render_sidebar_controls,
    _render_trading_tab,
)
from auto_trader.stateio import read_json_with_recovery

AUTO_REFRESH_SEC = 10.0


def main() -> None:
    # Note: page_config is set by the parent app.py
    _inject_ui_stability_styles()
    st.title("🔴 Live Monitor - Trading Operations")

    # Add refresh interval control
    refresh_interval = st.slider(
        "Auto-refresh interval (seconds)",
        min_value=5,
        max_value=120,
        value=30,
        step=5,
        help="Lower values = more frequent updates but higher CPU usage",
    )

    st.caption(f"Live Monitor auto-refreshes every {refresh_interval} seconds.")
    _render_sidebar_controls()

    # Load common data that all tabs need
    runtime_state = _load_runtime_state()
    worker_state = _load_worker_state()

    overview_tab, trading_tab, live_logs_tab = st.tabs(["Overview", "Trading", "Live Logs"])

    with overview_tab:
        # Load data only when overview tab is active
        gateway_state = read_json_with_recovery(DATA_DIR / "exchange" / "gateway_state.json")
        gateway_state = gateway_state if isinstance(gateway_state, dict) else {}
        risk_df = _read_optional(DATA_DIR / "risk" / "risk_eval.parquet")
        risk_input_df = _read_optional(DATA_DIR / "risk" / "risk_input.parquet")
        position_df = _read_optional(DATA_DIR / "positions" / "positions.parquet")
        regime_snapshot = _load_regime_snapshot()
        runtime_metrics = _load_runtime_metrics(DEFAULT_RUNTIME_METRICS_PATH)
        candidate_report = _load_candidate_report()
        weekly_candidate_report = _load_weekly_candidate_report()

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
        # Load data only when trading tab is active
        position_df = _read_optional(DATA_DIR / "positions" / "positions.parquet")
        risk_df = _read_optional(DATA_DIR / "risk" / "risk_eval.parquet")
        candidate_report = _load_candidate_report()
        weekly_candidate_report = _load_weekly_candidate_report()

        _render_trading_tab(
            worker_state=worker_state,
            position_df=position_df,
            risk_df=risk_df,
            candidate_report=weekly_candidate_report or candidate_report,
        )

    with live_logs_tab:
        # Load data only when live logs tab is active
        _render_live_logs_tab(runtime_metrics_path=DEFAULT_RUNTIME_METRICS_PATH)

    # Auto-rerun with custom interval for live monitor
    time.sleep(refresh_interval)
    st.rerun()


if __name__ == "__main__":
    main()
