from __future__ import annotations

import argparse
from pathlib import Path

from auto_trader.ml.pipeline import run_ml_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run ML filter pipeline.")
    p.add_argument("--features-path", required=True)
    p.add_argument("--regime-path", required=True)
    p.add_argument("--signals-path", required=True)
    p.add_argument("--labels-path", required=True)
    p.add_argument("--output-path", default="data/ml/scored.parquet")
    p.add_argument("--artifact-dir", default="data/ml/artifacts/latest")
    p.add_argument("--model-version", default="lgbm-entry-filter-v1")
    return p


def main() -> int:
    args = build_parser().parse_args()
    scored, _, trained = run_ml_pipeline(
        features_path=Path(args.features_path),
        regime_path=Path(args.regime_path),
        signals_path=Path(args.signals_path),
        labels_path=Path(args.labels_path),
        artifact_dir=Path(args.artifact_dir),
        model_version=args.model_version,
    )
    out_path = Path(args.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(out_path, index=False)
    print(
        f"saved={out_path} rows={len(scored)} threshold={trained.threshold:.2f} "
        f"valid_f1={trained.metrics['valid_f1']:.4f} "
        f"artifact={args.artifact_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
