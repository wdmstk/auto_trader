from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.risk.manager import (
    RiskConfig,
    RiskManager,
    ensure_correlated_exposure_column,
    evaluate_portfolio_risk,
)

_EMPTY_RISK_OUTPUT_COLUMNS: dict[str, str] = {
    "timestamp": "datetime64[ns, UTC]",
    "symbol": "object",
    "risk_blocked": "bool",
    "block_reason_codes": "object",
    "current_dd_pct": "float64",
    "portfolio_exposure_pct": "float64",
    "concentration_score": "float64",
    "correlated_exposure_pct": "float64",
    "vol_weighted_exposure_pct": "float64",
    "risk_contribution_pct": "float64",
    "missing_vol_ratio": "float64",
    "size_scale": "float64",
    "emergency_state": "bool",
}


def _empty_risk_output_frame() -> pd.DataFrame:
    frame = pd.DataFrame(
        {column: pd.Series(dtype=dtype) for column, dtype in _EMPTY_RISK_OUTPUT_COLUMNS.items()}
    )
    return frame[list(_EMPTY_RISK_OUTPUT_COLUMNS)]


def run_risk_pipeline(
    *,
    input_path: str | Path,
    output_path: str | Path = "data/risk/risk_eval.parquet",
    config: RiskConfig | None = None,
    emergency_state: bool = False,
) -> pd.DataFrame:
    inputs = pd.read_parquet(input_path)
    if inputs.empty:
        out = _empty_risk_output_frame()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(path, index=False)
        return out
    required = {"timestamp", "symbol", "current_equity", "equity_peak", "symbol_exposure_pct"}
    missing = sorted(required - set(inputs.columns))
    if missing:
        raise ValueError(f"risk input missing required columns: {', '.join(missing)}")
    inputs = ensure_correlated_exposure_column(inputs)
    manager = RiskManager(config)
    if emergency_state:
        manager.emergency_stop()
    out = evaluate_portfolio_risk(manager=manager, risk_inputs=inputs)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path, index=False)
    return out
