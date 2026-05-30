from __future__ import annotations

import argparse
import json
from pathlib import Path

from auto_trader.e2e.smoke import run_e2e_smoke


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run end-to-end smoke validation.")
    p.add_argument("--signals-path", required=True)
    p.add_argument("--risk-eval-path", required=True)
    p.add_argument("--runtime-state-path", required=True)
    p.add_argument("--output-dir", default="data/e2e")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    out = run_e2e_smoke(
        signals_path=Path(args.signals_path),
        risk_eval_path=Path(args.risk_eval_path),
        runtime_state_path=Path(args.runtime_state_path),
        output_dir=Path(args.output_dir),
    )
    print(json.dumps(out, ensure_ascii=True))
    return 0 if str(out["overall_status"]) == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
