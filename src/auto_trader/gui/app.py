from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from auto_trader.gui.overlay import build_overlay_frame
from auto_trader.gui.state import ControlEvent, append_control_event, emergency_badge, is_stale

DATA_DIR = Path("data")
CONTROL_LOG = DATA_DIR / "gui" / "control_events.jsonl"


def _read_optional(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()


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


def main() -> None:
    st.set_page_config(page_title="Auto Trader Ops Console", layout="wide")
    st.title("Auto Trader Operations Dashboard")

    risk_df = _read_optional(DATA_DIR / "risk" / "risk_eval.parquet")
    regime_df = _read_optional(DATA_DIR / "regime" / "BTCUSDT_1m_regime.parquet")
    position_df = _read_optional(DATA_DIR / "positions" / "positions.parquet")
    portfolio_df = _read_optional(DATA_DIR / "backtest" / "portfolio.parquet")
    ohlcv_df = _read_optional(DATA_DIR / "parquet" / "BTCUSDT_1m.parquet")
    signal_df = _read_optional(DATA_DIR / "signals" / "BTCUSDT_1m_range_signals.parquet")

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

    st.subheader("Chart Overlay")
    if not ohlcv_df.empty:
        overlay = build_overlay_frame(
            ohlcv_df=ohlcv_df,
            signal_df=signal_df,
            regime_df=regime_df,
            risk_df=risk_df,
        )
        if overlay.empty:
            st.info("Overlay data unavailable")
        else:
            chart = overlay.set_index("timestamp")
            st.line_chart(chart[["close", "entry_marker", "exit_marker", "risk_block_marker"]])
            st.line_chart(chart[["ml_score", "regime_band"]])
            st.caption("Overlay: close + entry/exit/risk markers, ml_score, regime_band")
    else:
        st.info("No OHLCV data available for chart")


if __name__ == "__main__":
    main()
