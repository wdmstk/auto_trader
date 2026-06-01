from __future__ import annotations

import importlib
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

try:
    alt: Any = importlib.import_module("altair")
except Exception:  # pragma: no cover - UI fallback
    alt = None

from auto_trader.gui.overlay import build_overlay_frame
from auto_trader.gui.state import ControlEvent, append_control_event, emergency_badge, is_stale

DATA_DIR = Path("data")
CONTROL_LOG = DATA_DIR / "gui" / "control_events.jsonl"
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]


@st.cache_data(ttl=10, show_spinner=False)  # type: ignore[misc]
def _read_optional_cached(path_str: str) -> pd.DataFrame:
    path = Path(path_str)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()


def _read_optional(path: Path) -> pd.DataFrame:
    return _read_optional_cached(str(path))


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


def _render_controls() -> None:
    st.subheader("Controls")
    col1, col2, col3, col4, col5 = st.columns(5)
    buttons = [
        ("START", col1),
        ("STOP", col2),
        ("EMERGENCY_STOP", col3),
        ("EMERGENCY_CANCEL", col4),
        ("CLOSE_ALL", col5),
    ]
    for action, col in buttons:
        if col.button(action, type="primary" if "EMERGENCY" in action else "secondary"):
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

    candle = (
        alt.Chart(frame)
        .mark_bar(size=5)
        .encode(
            x=alt.X("timestamp:T", title="timestamp"),
            y=alt.Y("open:Q", title="price"),
            y2="close:Q",
            color=alt.Color(
                "up:N", scale=alt.Scale(domain=["UP", "DOWN"], range=["#16a34a", "#dc2626"])
            ),
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
        .mark_point(shape="triangle-up", color="#2563eb", size=80)
        .encode(x="timestamp:T", y="close:Q")
    )
    exits = (
        alt.Chart(frame[frame["exit_signal"]])
        .mark_point(shape="triangle-down", color="#ea580c", size=80)
        .encode(x="timestamp:T", y="close:Q")
    )
    risk_block = (
        alt.Chart(frame[frame["risk_blocked"]])
        .mark_point(shape="cross", color="#7c3aed", size=70)
        .encode(x="timestamp:T", y="close:Q")
    )
    chart = (wick + candle + entries + exits + risk_block).properties(height=420).interactive()
    st.altair_chart(chart, use_container_width=True)
    st.caption("Candlestick + entry/exit/risk markers (drag/scroll to zoom)")


def _downsample_for_chart(df: pd.DataFrame, max_points: int) -> pd.DataFrame:
    if max_points <= 0 or len(df) <= max_points:
        return df
    step = max(1, math.ceil(len(df) / max_points))
    sampled = df.iloc[::step].copy()
    # Ensure the latest point is always visible.
    if sampled.index[-1] != df.index[-1]:
        sampled = pd.concat([sampled, df.tail(1)], axis=0).drop_duplicates()
    return sampled


def _symbol_snapshot(
    symbol: str,
    risk_df: pd.DataFrame,
    wf_range: dict[str, dict[str, float]],
    wf_trend: dict[str, dict[str, float]],
) -> dict[str, object]:
    regime_df = _read_optional(DATA_DIR / "regime" / f"{symbol}_1m_regime.parquet")
    range_df = _read_optional(DATA_DIR / "signals" / f"{symbol}_1m_range_signals.parquet")
    trend_df = _read_optional(DATA_DIR / "signals" / f"{symbol}_1m_trend_signals.parquet")
    ohlcv_df = _read_optional(DATA_DIR / "parquet" / f"{symbol}_1m.parquet")
    latest_regime = _latest_value(regime_df, "regime", default="UNKNOWN")
    last_close: float | str = "-"
    if not ohlcv_df.empty and "close" in ohlcv_df.columns:
        try:
            last_close = float(ohlcv_df.iloc[-1]["close"])
        except Exception:
            last_close = "-"
    range_entries = 0
    trend_entries = 0
    if not range_df.empty and "entry_signal" in range_df.columns:
        range_entries = int(
            pd.to_numeric(range_df["entry_signal"], errors="coerce").fillna(0).astype(bool).sum()
        )
    if not trend_df.empty and "entry_signal" in trend_df.columns:
        trend_entries = int(
            pd.to_numeric(trend_df["entry_signal"], errors="coerce").fillna(0).astype(bool).sum()
        )
    exposure: float | str = "-"
    dd: float | str = "-"
    vwe: float | str = "-"
    rc: float | str = "-"
    scale: float | str = "-"
    if not risk_df.empty:
        s = risk_df[risk_df.get("symbol", pd.Series(dtype=str)).astype(str) == symbol]
        if not s.empty:
            if "portfolio_exposure_pct" in s.columns:
                exposure = float(
                    pd.to_numeric(s["portfolio_exposure_pct"], errors="coerce").fillna(0.0).iloc[-1]
                )
            if "current_dd_pct" in s.columns:
                dd = float(pd.to_numeric(s["current_dd_pct"], errors="coerce").fillna(0.0).iloc[-1])
            if "vol_weighted_exposure_pct" in s.columns:
                vwe = float(
                    pd.to_numeric(s["vol_weighted_exposure_pct"], errors="coerce")
                    .fillna(0.0)
                    .iloc[-1]
                )
            if "risk_contribution_pct" in s.columns:
                rc = float(
                    pd.to_numeric(s["risk_contribution_pct"], errors="coerce").fillna(0.0).iloc[-1]
                )
            if "size_scale" in s.columns:
                scale = float(pd.to_numeric(s["size_scale"], errors="coerce").fillna(1.0).iloc[-1])
    pnl = float(wf_range.get(symbol, {}).get("monthly_pnl", 0.0)) + float(
        wf_trend.get(symbol, {}).get("monthly_pnl", 0.0)
    )
    return {
        "symbol": symbol,
        "regime": latest_regime,
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


def _load_walkforward_metric_map(
    strategy: str, symbols: list[str], timeframe: str = "1m"
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        df = _read_walkforward_summary(symbol=symbol, timeframe=timeframe, strategy=strategy)
        if df.empty:
            out[symbol] = {"pf": 0.0, "win_rate": 0.0, "max_dd": 0.0, "monthly_pnl": 0.0}
            continue
        pf = float(
            pd.to_numeric(df.get("pf", pd.Series([0.0])), errors="coerce").fillna(0.0).mean()
        )
        wr = float(
            pd.to_numeric(df.get("win_rate", pd.Series([0.0])), errors="coerce").fillna(0.0).mean()
        )
        dd = float(
            pd.to_numeric(df.get("max_dd", pd.Series([0.0])), errors="coerce").fillna(0.0).mean()
        )
        pnl = float(
            pd.to_numeric(df.get("monthly_pnl", pd.Series([0.0])), errors="coerce")
            .fillna(0.0)
            .mean()
        )
        out[symbol] = {"pf": pf, "win_rate": wr, "max_dd": dd, "monthly_pnl": pnl}
    return out


def _load_walkforward_artifact(
    symbol: str, timeframe: str, strategy: str, kind: str
) -> pd.DataFrame:
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
        value=",".join(DEFAULT_SYMBOLS),
        key="symbols_input",
    )
    max_symbols = st.slider("Max symbols to render", min_value=2, max_value=20, value=8, step=1)
    enable_heavy = st.checkbox(
        "Enable heavy visualizations (correlation/walkforward tables)", value=False
    )
    corr_rows = st.slider(
        "Rows per symbol for correlation", min_value=300, max_value=5000, value=1500, step=100
    )
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
    snap["wf_range_win_rate"] = snap["symbol"].map(
        lambda s: wf_range.get(str(s), {}).get("win_rate", 0.0)
    )
    snap["wf_range_max_dd"] = snap["symbol"].map(
        lambda s: wf_range.get(str(s), {}).get("max_dd", 0.0)
    )
    snap["wf_range_monthly_pnl"] = snap["symbol"].map(
        lambda s: wf_range.get(str(s), {}).get("monthly_pnl", 0.0)
    )
    snap["wf_trend_pf"] = snap["symbol"].map(lambda s: wf_trend.get(str(s), {}).get("pf", 0.0))
    snap["wf_trend_win_rate"] = snap["symbol"].map(
        lambda s: wf_trend.get(str(s), {}).get("win_rate", 0.0)
    )
    snap["wf_trend_max_dd"] = snap["symbol"].map(
        lambda s: wf_trend.get(str(s), {}).get("max_dd", 0.0)
    )
    snap["wf_trend_monthly_pnl"] = snap["symbol"].map(
        lambda s: wf_trend.get(str(s), {}).get("monthly_pnl", 0.0)
    )

    st.dataframe(snap, use_container_width=True)

    if not snap.empty:
        st.caption("Regime map")
        mapping = {"RANGE": 1.0, "TREND": 2.0, "HIGH_VOL": 3.0, "UNKNOWN": 0.0}
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
        risk_rank = risk_rank.sort_values(
            ["risk_contribution_pct", "vol_weighted_exposure_pct"], ascending=False
        )
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
                    corr_long = corr.reset_index().melt(
                        id_vars="index", var_name="symbol_y", value_name="corr"
                    )
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
                                    domain=[-1, 0, 1], range=["#2563eb", "#f8fafc", "#dc2626"]
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
    st.caption(
        f"runtime_trading_enabled={runtime_trading}, runtime_emergency_stop={emergency_stop}, "
        f"timestamp={latest.get('timestamp', '-')}"
    )
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


def main() -> None:
    st.set_page_config(page_title="Auto Trader Ops Console", layout="wide")
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
    elif badge == "HIGH_VOL":
        st.warning("HIGH_VOL DETECTED")
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
        f"vol_weighted_exposure_pct={_latest_value(risk_df, 'vol_weighted_exposure_pct', '-')}, "
        f"size_scale={_latest_value(risk_df, 'size_scale', '-')}"
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
        overlay_strategy = st.selectbox(
            "Overlay Strategy", options=["range", "trend"], index=0, key="overlay_strategy"
        )
        signal_df = _read_optional(
            DATA_DIR / "signals" / f"BTCUSDT_1m_{overlay_strategy}_signals.parquet"
        )
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
        overlay = build_overlay_frame(
            ohlcv_df=ohlcv_df,
            signal_df=signal_df,
            regime_df=regime_df,
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
        wf_symbol = st.selectbox("WF Symbol", options=DEFAULT_SYMBOLS, index=0, key="wf_symbol")
        wf_summary = _load_walkforward_artifact(wf_symbol, "1m", strategy, "summary")

        if wf_summary.empty:
            st.info("No walkforward report found. Run `python -m auto_trader.analysis ...` first.")
        else:
            st.caption("Fold summary: PF/WinRate/DD/PnL and invalid regime entries")
            st.dataframe(wf_summary, use_container_width=True)
            wf_fast_mode = st.checkbox("Walkforward Fast Mode", value=True, key="wf_fast_mode")
            show_wf_details = st.checkbox("Show Walkforward Details", value=False, key="wf_details")
            if show_wf_details:
                max_portfolio_rows = st.slider(
                    "WF Portfolio Rows", min_value=200, max_value=5000, value=1000, step=100
                )
                max_trade_rows = st.slider(
                    "WF Trade Rows", min_value=50, max_value=2000, value=300, step=50
                )

                wf_portfolio = _load_walkforward_artifact(wf_symbol, "1m", strategy, "portfolio")
                wf_trades = _load_walkforward_artifact(wf_symbol, "1m", strategy, "trades")
                wf_regime = _load_walkforward_artifact(wf_symbol, "1m", strategy, "regime_counts")
                wf_invalid = _load_walkforward_artifact(
                    wf_symbol, "1m", strategy, "invalid_entries"
                )

                if not wf_portfolio.empty and {"timestamp", "equity", "fold"}.issubset(
                    wf_portfolio.columns
                ):
                    p = wf_portfolio.tail(max_portfolio_rows).copy()
                    p["timestamp"] = pd.to_datetime(p["timestamp"], utc=True)
                    p = p.sort_values(["fold", "timestamp"])
                    if wf_fast_mode:
                        p = _downsample_for_chart(p, max_points=1000)
                    st.line_chart(p.set_index("timestamp")[["equity"]])
                if not wf_trades.empty and {"timestamp", "side", "price", "fold"}.issubset(
                    wf_trades.columns
                ):
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


if __name__ == "__main__":
    main()
