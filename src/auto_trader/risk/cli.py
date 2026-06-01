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
    p.add_argument("--max-correlated-exposure-pct", type=float, default=50.0)
    p.add_argument("--soft-vol-weighted-exposure-pct", type=float, default=45.0)
    p.add_argument("--max-vol-weighted-exposure-pct", type=float, default=60.0)
    p.add_argument("--max-risk-contribution-pct", type=float, default=55.0)
    p.add_argument("--min-size-scale", type=float, default=0.25)
    p.add_argument("--fallback-size-scale-missing-vol", type=float, default=0.5)
    p.add_argument("--max-missing-vol-ratio", type=float, default=0.2)
    p.add_argument("--emergency-stop", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    cfg = RiskConfig(
        max_dd_pct=args.max_dd_pct,
        max_symbol_exposure_pct=args.max_symbol_exposure_pct,
        max_portfolio_exposure_pct=args.max_portfolio_exposure_pct,
        max_concentration_score=args.max_concentration_score,
        max_correlated_exposure_pct=args.max_correlated_exposure_pct,
        soft_vol_weighted_exposure_pct=args.soft_vol_weighted_exposure_pct,
        max_vol_weighted_exposure_pct=args.max_vol_weighted_exposure_pct,
        max_risk_contribution_pct=args.max_risk_contribution_pct,
        min_size_scale=args.min_size_scale,
        fallback_size_scale_missing_vol=args.fallback_size_scale_missing_vol,
        max_missing_vol_ratio=args.max_missing_vol_ratio,
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
