"""Analysis Workspace page for deep analysis and backtesting."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pandas as pd
import streamlit as st

from auto_trader.gui.data_loader import (
    DATA_DIR,
    DEFAULT_RUNTIME_METRICS_PATH,
    _active_worker_symbols,
    _build_return_matrix,
    _candidate_frame,
    _core_symbol_focus_rows,
    _discover_available_symbols,
    _discover_backtest_runs,
    _load_candidate_report,
    _load_regime_snapshot,
    _load_walkforward_artifact,
    _load_walkforward_metric_map,
    _load_weekly_candidate_report,
    _load_worker_state,
    _manifest_weekly_diff_rows,
    _preferred_symbol_choices,
    _read_optional,
    _route_selection_path,
    _source_snapshot,
    _strategy_symbol_table,
    _symbol_snapshot,
    _weekly_revalidation_report_path,
)
from auto_trader.gui.overlay import build_overlay_frame
from auto_trader.gui.ui_components import (
    _inject_ui_stability_styles,
    _render_candlestick_overlay,
    _render_range_probe_candidates,
)
from auto_trader.gui.utils import (
    downsample_for_chart as _downsample_for_chart,
)
from auto_trader.gui.utils import (
    safe_float as _safe_float,
)
from auto_trader.gui.utils import (
    worker_state_key_parts,
)
from auto_trader.worker.state import WorkerState

try:
    import importlib

    alt: Any = importlib.import_module("altair")
except Exception:
    alt = None


def main() -> None:
    # Note: page_config is set by the parent app.py
    _inject_ui_stability_styles()
    st.title("📊 Analysis Workspace - Deep Analysis")

    st.caption("This workspace does not auto-refresh. Rerun manually after generating new analysis artifacts.")

    # Load data for analysis
    risk_df = _read_optional(DATA_DIR / "risk" / "risk_eval.parquet")
    portfolio_df = _read_optional(DATA_DIR / "backtest" / "portfolio.parquet")
    ohlcv_df = _read_optional(DATA_DIR / "parquet" / "BTCUSDT_1m.parquet")
    backtest_runs = _discover_backtest_runs()
    candidate_report = _load_candidate_report()
    weekly_candidate_report = _load_weekly_candidate_report()

    # Load worker state for moved components
    worker_state = _load_worker_state()

    charts_tab, analysis_tab, audit_tab = st.tabs(["Charts", "Analysis", "Audit"])

    with charts_tab:
        _render_charts_tab(
            risk_df=risk_df,
            ohlcv_df=ohlcv_df,
            candidate_report=candidate_report,
        )

    with analysis_tab:
        _render_analysis_tab(
            portfolio_df=portfolio_df,
            backtest_runs=backtest_runs,
            candidate_report=candidate_report,
            weekly_candidate_report=weekly_candidate_report,
            worker_state=worker_state,
        )

    with audit_tab:
        _render_audit_tab(weekly_report=weekly_candidate_report)


def _render_charts_tab(
    *,
    risk_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
    candidate_report: dict[str, object],
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


def _render_analysis_tab(
    *,
    portfolio_df: pd.DataFrame,
    backtest_runs: list[dict[str, object]],
    candidate_report: dict[str, object],
    weekly_candidate_report: dict[str, object] | None,
    worker_state: WorkerState,
) -> None:
    st.subheader("Analysis")
    st.caption("Heavy analysis is opt-in to keep the live console fast.")

    # Moved components from Live Monitor
    _render_moved_analysis_components(candidate_report, weekly_candidate_report, worker_state)

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


def _render_moved_analysis_components(
    candidate_report: dict[str, object],
    weekly_candidate_report: dict[str, object] | None,
    worker_state: WorkerState,
) -> None:
    """Render components moved from Live Monitor to Analysis Workspace."""
    st.subheader("Strategy Performance Tables (Moved from Live Monitor)")
    st.caption("These tables provide detailed strategy performance analysis.")

    risk_df = _read_optional(DATA_DIR / "risk" / "risk_eval.parquet")

    # Calculate common variables
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
    regime_symbols = sorted(set(active_symbols) | set(candidate_symbols))

    with st.expander("Strategy performance tables", expanded=False):
        candidate_rows = _candidate_frame(candidate_report)
        candidate_watchlist = _candidate_frame(candidate_report, "watchlist")
        best_rows = candidate_report.get("best_by_symbol_strategy", [])
        candidate_status_map: dict[str, str] = {}
        if isinstance(best_rows, list):
            for row in best_rows:
                if isinstance(row, dict):
                    row_map = cast(dict[str, object], row)
                    candidate_status_map[str(row_map.get("symbol", ""))] = str(row_map.get("candidate_status", ""))
        watchlist_symbols = (
            sorted(candidate_watchlist["symbol"].astype(str).unique().tolist())
            if not candidate_watchlist.empty and "symbol" in candidate_watchlist.columns
            else []
        )
        show_core = st.checkbox("Show core", value=True, key="analysis_symbols_show_core")
        show_watchlist = st.checkbox("Show watchlist", value=False, key="analysis_symbols_show_watchlist")
        show_probe = st.checkbox("Show probe", value=False, key="analysis_symbols_show_probe")
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

    # Range probe candidates
    _render_range_probe_candidates(candidate_report)

    # Last processed bars (moved from Trading tab)
    st.subheader("Last Processed Bars (Moved from Live Monitor)")
    if not worker_state.last_processed_bars:
        st.info("No processed bars yet.")
    else:
        rows = []
        for key, ts in sorted(worker_state.last_processed_bars.items()):
            route, symbol, timeframe = worker_state_key_parts(key)
            rows.append(
                {
                    "route": route,
                    "symbol": symbol,
                    "timeframe": timeframe or "-",
                    "last_processed_bar": ts,
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

    # Regime by symbol (moved from Overview)
    st.subheader("Regime by Symbol (Moved from Live Monitor)")
    regime_snapshot = _load_regime_snapshot()

    # Recalculate watchlist_symbols for regime section
    candidate_watchlist = _candidate_frame(candidate_report, "watchlist")
    watchlist_symbols = (
        sorted(candidate_watchlist["symbol"].astype(str).unique().tolist()) if not candidate_watchlist.empty and "symbol" in candidate_watchlist.columns else []
    )

    if not regime_symbols:
        st.info("No symbols available for regime view.")
    else:
        regime_view = regime_snapshot[regime_snapshot["symbol"].isin(regime_symbols)].copy()
        if regime_view.empty:
            st.info("No regime parquet files found for watchlist or active symbols.")
        else:
            show_active = st.checkbox("Show active", value=True, key="analysis_regime_show_active")
            show_watchlist = st.checkbox("Show watchlist", value=False, key="analysis_regime_show_watchlist")
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


def _render_audit_tab(*, weekly_report: dict[str, object] | None) -> None:
    st.subheader("Audit")
    st.caption("Weekly route-validation and drift comparison. Manual refresh only.")

    # Moved Data sources from Live Monitor
    st.subheader("Data Sources (Moved from Live Monitor)")
    runtime_env_path = DATA_DIR / "validation" / "weekly_autotune" / "route_selection_runtime.env"
    runtime_route_path = _route_selection_path()
    weekly_report_path = _weekly_revalidation_report_path()
    position_df = _read_optional(DATA_DIR / "positions" / "positions.parquet")
    risk_df = _read_optional(DATA_DIR / "risk" / "risk_eval.parquet")
    risk_input_df = _read_optional(DATA_DIR / "risk" / "risk_input.parquet")

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

    # Manifest vs weekly diff
    _render_manifest_weekly_diff_section(weekly_report)


def _render_manifest_weekly_diff_section(weekly_report: dict[str, object] | None) -> None:
    manifest_diff_rows = _manifest_weekly_diff_rows(weekly_report)
    if not manifest_diff_rows:
        st.info("No manifest-vs-weekly diff summary is available.")
        return
    st.subheader("Manifest vs Weekly drift")
    diff_summary: dict[str, object] = {}
    if isinstance(weekly_report, dict):
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


if __name__ == "__main__":
    main()
