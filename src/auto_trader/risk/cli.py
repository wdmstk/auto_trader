from __future__ import annotations

import argparse
from pathlib import Path

from auto_trader.risk.manager import RiskConfig
from auto_trader.risk.pipeline import run_risk_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run risk management evaluation.")
    p.add_argument("--input-path", required=True)
    p.add_argument("--output-path", default="data/risk/risk_eval.parquet")
    p.add_argument("--max-dd-pct", type=float, default=15.0)
    p.add_argument("--max-symbol-exposure-pct", type=float, default=25.0)
    p.add_argument("--max-portfolio-exposure-pct", type=float, default=70.0)
    p.add_argument("--max-concentration-score", type=float, default=0.6)
    p.add_argument("--emergency-stop", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    cfg = RiskConfig(
        max_dd_pct=args.max_dd_pct,
        max_symbol_exposure_pct=args.max_symbol_exposure_pct,
        max_portfolio_exposure_pct=args.max_portfolio_exposure_pct,
        max_concentration_score=args.max_concentration_score,
    )
    out = run_risk_pipeline(
        input_path=Path(args.input_path),
        output_path=Path(args.output_path),
        config=cfg,
        emergency_state=bool(args.emergency_stop),
    )
    blocked = int(out["risk_blocked"].sum()) if "risk_blocked" in out.columns else 0
    print(f"rows={len(out)} blocked={blocked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
