from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from auto_trader.drift.metrics import (
    build_baseline_stats,
    evaluate_drift,
    load_baseline,
    save_baseline,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Feature drift check (PSI-based).")
    p.add_argument("--features-path", default=None)
    p.add_argument("--features-glob", default=None)
    p.add_argument("--baseline-path", default="data/validation/drift/baseline_stats.json")
    p.add_argument("--report-path", default="data/validation/drift/feature_drift_report.json")
    p.add_argument("--online-stats-path", default="data/validation/drift/online_stats_latest.json")
    p.add_argument("--bins", type=int, default=10)
    p.add_argument("--write-baseline-if-missing", default="true")
    return p


def _load_features(path: str | None, pattern: str | None) -> pd.DataFrame:
    paths: list[Path] = []
    if path:
        paths.append(Path(path))
    if pattern:
        paths.extend(sorted(Path().glob(pattern)))
    uniq = []
    seen = set()
    for p in paths:
        key = str(p)
        if key not in seen and p.exists():
            uniq.append(p)
            seen.add(key)
    if not uniq:
        raise SystemExit("no feature files found")
    parts = [pd.read_parquet(p) for p in uniq]
    return pd.concat(parts, axis=0, ignore_index=True)


def main() -> int:
    args = _build_parser().parse_args()
    baseline_path = Path(args.baseline_path)
    report_path = Path(args.report_path)
    online_stats_path = Path(args.online_stats_path)
    write_baseline = str(args.write_baseline_if_missing).lower() in {"1", "true", "yes", "on"}

    features = _load_features(args.features_path, args.features_glob)
    baseline = load_baseline(baseline_path)

    baseline_created = False
    if not baseline:
        if write_baseline:
            baseline = build_baseline_stats(features, bins=max(int(args.bins), 2))
            save_baseline(baseline_path, baseline)
            baseline_created = True
        else:
            out = {
                "checked_at": datetime.now(UTC).isoformat(),
                "status": "warn",
                "drift_trade_block": False,
                "reason": "baseline_missing",
            }
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(out, ensure_ascii=True, indent=2), encoding="utf-8")
            print(report_path)
            return 0

    result = evaluate_drift(features, baseline)
    result["checked_at"] = datetime.now(UTC).isoformat()
    result["baseline_path"] = str(baseline_path)
    result["baseline_created"] = baseline_created
    if baseline_created and result["status"] == "pass":
        result["status"] = "warn"
        result["bootstrap_note"] = "baseline_created_first_run"

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    online_stats = build_baseline_stats(features, bins=max(int(args.bins), 2))
    online_stats["checked_at"] = datetime.now(UTC).isoformat()
    online_stats_path.parent.mkdir(parents=True, exist_ok=True)
    online_stats_path.write_text(
        json.dumps(online_stats, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
