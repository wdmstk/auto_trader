from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pandas as pd

from auto_trader.utils import write_json_file


@dataclass(frozen=True)
class DriftThresholds:
    warn_psi: float = 0.1
    fail_psi: float = 0.25
    warn_fail_feature_ratio: float = 0.10
    fail_fail_feature_ratio: float = 0.30
    fail_missing_feature_ratio: float = 0.30


def _numeric_feature_columns(df: pd.DataFrame) -> list[str]:
    exclude = {"timestamp", "is_warmup"}
    cols = []
    for c in df.columns:
        if c in exclude:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append(c)
    return cols


def _safe_hist(series: pd.Series, bins: int) -> tuple[list[float], list[float]]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        edges = [0.0, 1.0]
        return [1.0], edges
    # Use pd.cut to avoid plotting side effects.
    cats = pd.cut(s.astype(float), bins=bins, include_lowest=True)
    counts = cats.value_counts(sort=False)
    probs = (counts / max(float(counts.sum()), 1.0)).astype(float).tolist()
    edges = [float(c.left) for c in counts.index] + [float(counts.index[-1].right)]
    return probs, edges


def _psi(expected: list[float], actual: list[float], eps: float = 1e-6) -> float:
    n = min(len(expected), len(actual))
    e = [max(float(expected[i]), eps) for i in range(n)]
    a = [max(float(actual[i]), eps) for i in range(n)]
    return float(sum((ai - ei) * __import__("math").log(ai / ei) for ai, ei in zip(a, e, strict=False)))


def build_baseline_stats(df: pd.DataFrame, *, bins: int = 10) -> dict[str, object]:
    features = _numeric_feature_columns(df)
    out: dict[str, object] = {"features": {}, "bins": bins}
    features_out = cast(dict[str, dict[str, object]], out["features"])
    for f in features:
        s = pd.to_numeric(df[f], errors="coerce")
        probs, edges = _safe_hist(s, bins=bins)
        features_out[f] = {
            "mean": float(s.mean(skipna=True)),
            "std": float(s.std(skipna=True) if s.count() > 1 else 0.0),
            "histogram_probs": probs,
            "histogram_edges": edges,
        }
    return out


def save_baseline(path: Path, baseline: dict[str, object]) -> None:
    write_json_file(path, baseline)


def load_baseline(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def evaluate_drift(
    df: pd.DataFrame,
    baseline: dict[str, object],
    *,
    thresholds: DriftThresholds | None = None,
) -> dict[str, object]:
    t = thresholds or DriftThresholds()
    feat_obj = baseline.get("features", {}) if isinstance(baseline, dict) else {}
    baseline_features = feat_obj if isinstance(feat_obj, dict) else {}

    rows: list[dict[str, object]] = []
    missing = 0
    fail_count = 0
    total = 0

    for f in _numeric_feature_columns(df):
        total += 1
        if f not in baseline_features:
            missing += 1
            rows.append({"feature": f, "status": "unknown", "psi": None})
            continue

        b = baseline_features[f]
        if not isinstance(b, dict):
            missing += 1
            rows.append({"feature": f, "status": "unknown", "psi": None})
            continue

        bins = b.get("histogram_edges")
        expected = b.get("histogram_probs")
        if not isinstance(bins, list) or len(bins) < 2 or not isinstance(expected, list):
            missing += 1
            rows.append({"feature": f, "status": "unknown", "psi": None})
            continue

        s = pd.to_numeric(df[f], errors="coerce").dropna().astype(float)
        if s.empty:
            missing += 1
            rows.append({"feature": f, "status": "unknown", "psi": None})
            continue

        cats = pd.cut(s, bins=bins, include_lowest=True)
        counts = cats.value_counts(sort=False)
        actual = (counts / max(float(counts.sum()), 1.0)).astype(float).tolist()
        psi_val = _psi([float(x) for x in expected], actual)

        b_mean = float(b.get("mean", 0.0))
        b_std = float(b.get("std", 0.0))
        c_mean = float(s.mean())
        c_std = float(s.std() if s.count() > 1 else 0.0)
        mean_delta_z = abs(c_mean - b_mean) / max(abs(b_std), 1e-9)
        std_ratio = (c_std / max(abs(b_std), 1e-9)) if abs(b_std) > 0 else 0.0

        status = "pass"
        if psi_val >= t.fail_psi:
            status = "fail"
            fail_count += 1
        elif psi_val >= t.warn_psi:
            status = "warn"

        rows.append(
            {
                "feature": f,
                "status": status,
                "psi": float(psi_val),
                "mean_delta_z": float(mean_delta_z),
                "std_ratio": float(std_ratio),
            }
        )

    fail_ratio = (fail_count / total) if total else 0.0
    missing_ratio = (missing / total) if total else 1.0

    overall = "pass"
    if fail_ratio >= t.fail_fail_feature_ratio or missing_ratio >= t.fail_missing_feature_ratio:
        overall = "fail"
    elif fail_ratio >= t.warn_fail_feature_ratio or missing > 0:
        overall = "warn"

    return {
        "status": overall,
        "drift_trade_block": bool(overall == "fail"),
        "total_features": total,
        "fail_features": fail_count,
        "missing_features": missing,
        "fail_feature_ratio": float(fail_ratio),
        "missing_feature_ratio": float(missing_ratio),
        "features": rows,
    }
