from __future__ import annotations

from pathlib import Path

import pandas as pd

from auto_trader.risk.manager import RiskConfig, RiskManager, evaluate_portfolio_risk


def run_risk_pipeline(
    *,
    input_path: str | Path,
    output_path: str | Path = "data/risk/risk_eval.parquet",
    config: RiskConfig | None = None,
    emergency_state: bool = False,
) -> pd.DataFrame:
    inputs = pd.read_parquet(input_path)
    manager = RiskManager(config)
    if emergency_state:
        manager.emergency_stop()
    out = evaluate_portfolio_risk(manager=manager, risk_inputs=inputs)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path, index=False)
    return out
