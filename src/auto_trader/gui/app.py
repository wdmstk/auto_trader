from __future__ import annotations

# mypy: disable-error-code=misc
import sys
import time
import types
from datetime import UTC, datetime

import pandas as pd
import streamlit as st

import auto_trader.gui.data_loader as _data_loader
from auto_trader.gui.data_loader import (  # noqa: F401 – re-exported for tests
    _GUI_ENV_LOADED,
    DATA_DIR,
    REPO_ROOT,
    _active_worker_symbols,
    _candidate_frame,
    _candidate_trade_routes_frame,
    _core_symbol_focus_rows,
    _discover_available_symbols,
    _discover_backtest_runs,
    _discover_symbol_timeframes,
    _load_candidate_report,
    _load_walkforward_artifact,
    _load_weekly_candidate_report,
    _manifest_weekly_diff_rows,
    _operator_summary,
    _position_reconciliation_frame,
    _read_optional,
    _read_optional_cached,
    _resolve_futures_testnet_credentials,
    _route_selection_path,
    _weekly_revalidation_report_path,
    _worker_trade_routes_frame,
)
from auto_trader.gui.overlay import build_overlay_frame
from auto_trader.gui.state import emergency_badge, is_stale
from auto_trader.gui.ui_components import (
    CONTROL_LOG,
    _inject_ui_stability_styles,
    _render_candlestick_overlay,
    _render_controls,
    _render_drift_panel,
    _render_multi_symbol_panel,
    _render_runtime_metrics_panel,
)
from auto_trader.gui.ui_tabs import (
    _render_analysis_workspace,
    _render_live_monitor,
    _render_sidebar_controls,
)
from auto_trader.gui.utils import (
    downsample_for_chart as _downsample_for_chart,
)
from auto_trader.gui.utils import (
    latest_value as _latest_value,
)

# Propagate monkeypatch attribute changes to data_loader so tests that patch
# gui_app.DATA_DIR (etc.) affect the functions that now live in data_loader.
_PROPAGATE = frozenset({"DATA_DIR", "REPO_ROOT", "_GUI_ENV_LOADED"})


class _Module(types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if name in _PROPAGATE:
            setattr(_data_loader, name, value)


sys.modules[__name__].__class__ = _Module


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
    st.caption(f"vol_weighted_exposure_pct={_latest_value(risk_df, 'vol_weighted_exposure_pct', '-')}, size_scale={_latest_value(risk_df, 'size_scale', '-')}")

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

    # Add refresh interval control in sidebar
    with st.sidebar:
        refresh_interval = st.slider(
            "Auto-refresh interval (seconds)", min_value=5, max_value=120, value=30, step=5, help="Lower values = more frequent updates but higher CPU usage"
        )

    st.caption(f"Live Monitor auto-refreshes every {refresh_interval} seconds. " "Analysis Workspace refreshes only on manual rerun.")
    _render_sidebar_controls()
    live_tab, analysis_tab = st.tabs(["Live Monitor", "Analysis Workspace"])
    with live_tab:
        _render_live_monitor()
    with analysis_tab:
        _render_analysis_workspace()

    # Auto-rerun with custom interval for live monitor
    if st.session_state.get("active_tab") == "Live Monitor":
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
