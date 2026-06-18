from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from lightgbm import LGBMClassifier

from auto_trader.utils import write_json_file

KEY_COLS = ["symbol", "timeframe", "timestamp"]


@dataclass(frozen=True)
class ModelArtifacts:
    model: LGBMClassifier
    threshold: float
    metrics: dict[str, float]
    model_version: str
    feature_version: str
    train_range: dict[str, str]
    feature_columns: list[str]


def train_binary_classifier(
    *,
    dataset: pd.DataFrame,
    feature_columns: list[str],
    model_version: str = "lgbm-entry-filter-v1",
) -> ModelArtifacts:
    train = dataset[dataset["split"] == "train"]
    valid = dataset[dataset["split"] == "valid"]
    if train.empty or valid.empty:
        raise ValueError("train/valid split must not be empty")
    if not feature_columns:
        raise ValueError("feature_columns must not be empty")

    x_train = train[feature_columns]
    y_train = train["label"].astype(int)
    x_valid = valid[feature_columns]
    y_valid = valid["label"].astype(int)

    model = LGBMClassifier(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=-1,
        objective="binary",
        random_state=42,
    )
    model.fit(x_train, y_train)

    valid_score = pd.Series(model.predict_proba(x_valid)[:, 1], index=valid.index)
    threshold = optimize_threshold(y_valid, valid_score)
    pred = (valid_score >= threshold).astype(int)
    acc = float((pred == y_valid).mean())
    precision, recall, f1 = _precision_recall_f1(y_valid, pred)
    feature_version = _infer_single_value(dataset, "feature_version", default="unknown")
    train_range = _train_range(train)
    metrics = {
        "valid_accuracy": acc,
        "valid_precision": precision,
        "valid_recall": recall,
        "valid_f1": f1,
        "threshold": threshold,
        "train_rows": float(len(train)),
        "valid_rows": float(len(valid)),
    }
    return ModelArtifacts(
        model=model,
        threshold=threshold,
        metrics=metrics,
        model_version=model_version,
        feature_version=feature_version,
        train_range=train_range,
        feature_columns=list(feature_columns),
    )


def optimize_threshold(y_true: pd.Series, score: pd.Series) -> float:
    best_t = 0.5
    best_f1 = -1.0
    best_precision = -1.0
    for i in range(20, 81):
        t = i / 100.0
        pred = (score >= t).astype(int)
        precision, _, f1 = _precision_recall_f1(y_true, pred)
        if (f1 > best_f1) or (f1 == best_f1 and precision > best_precision):
            best_f1 = f1
            best_precision = precision
            best_t = t
    return best_t


def apply_model_filter(
    *,
    model: LGBMClassifier,
    threshold: float,
    dataset: pd.DataFrame,
    feature_columns: list[str],
) -> pd.DataFrame:
    out = dataset.copy()
    score = model.predict_proba(out[feature_columns])[:, 1]
    out["ml_score"] = score
    out["threshold"] = threshold
    out["pass_filter"] = out["ml_score"] >= threshold
    return out


def apply_model_artifacts(
    *,
    dataset: pd.DataFrame,
    artifacts: ModelArtifacts,
) -> pd.DataFrame:
    out = _normalize_keys(dataset)
    _validate_feature_version(out, artifacts.feature_version)
    _validate_feature_columns(out, artifacts.feature_columns)

    score = artifacts.model.predict_proba(out[artifacts.feature_columns])[:, 1]
    out["ml_score"] = score
    out["ml_threshold"] = artifacts.threshold
    out["ml_pass_filter"] = out["ml_score"] >= artifacts.threshold
    out["ml_model_version"] = artifacts.model_version
    out["ml_feature_version"] = artifacts.feature_version
    out["ml_train_start"] = artifacts.train_range.get("start", "")
    out["ml_train_end"] = artifacts.train_range.get("end", "")
    if "pass_filter" in out.columns:
        out["pass_filter"] = out["pass_filter"].fillna(False).astype(bool) & out["ml_pass_filter"]
    else:
        out["pass_filter"] = out["ml_pass_filter"]
    return out


def save_model_artifacts(artifacts: ModelArtifacts, artifact_dir: str | Path) -> str:
    out_dir = Path(artifact_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "model.pkl"
    meta_path = out_dir / "metadata.json"
    with model_path.open("wb") as f:
        pickle.dump(artifacts.model, f)
    meta = {
        "artifact_schema_version": 1,
        "model_version": artifacts.model_version,
        "feature_version": artifacts.feature_version,
        "train_range": artifacts.train_range,
        "threshold": artifacts.threshold,
        "metrics": artifacts.metrics,
        "feature_columns": artifacts.feature_columns,
        "model_filename": model_path.name,
    }
    write_json_file(meta_path, meta)
    return str(meta_path)


def load_model_artifacts(artifact_path: str | Path) -> ModelArtifacts:
    path = Path(artifact_path)
    meta_path = path
    if path.is_dir():
        meta_path = path / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"model artifact metadata not found: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(meta, dict):
        raise ValueError("invalid model artifact metadata")
    model_filename = str(meta.get("model_filename", "model.pkl"))
    model_path = meta_path.parent / model_filename
    if not model_path.exists():
        raise FileNotFoundError(f"model artifact payload not found: {model_path}")
    with model_path.open("rb") as f:
        model = pickle.load(f)
    if not isinstance(model, LGBMClassifier):
        raise ValueError("invalid model artifact payload")
    return ModelArtifacts(
        model=model,
        threshold=float(meta.get("threshold", 0.5)),
        metrics={str(k): float(v) for k, v in dict(meta.get("metrics", {})).items()},
        model_version=str(meta.get("model_version", "unknown")),
        feature_version=str(meta.get("feature_version", "unknown")),
        train_range={
            "start": str(dict(meta.get("train_range", {})).get("start", "")),
            "end": str(dict(meta.get("train_range", {})).get("end", "")),
        },
        feature_columns=[str(c) for c in list(meta.get("feature_columns", []))],
    )


def _validate_feature_columns(df: pd.DataFrame, feature_columns: list[str]) -> None:
    missing = [c for c in feature_columns if c not in df.columns]
    if missing:
        raise ValueError(f"missing feature columns for model inference: {missing}")


def _validate_feature_version(df: pd.DataFrame, expected: str) -> None:
    if "feature_version" not in df.columns:
        if expected == "unknown":
            return
        raise ValueError("feature_version missing for model inference")
    versions = {str(v) for v in df["feature_version"].dropna().astype(str).tolist() if str(v).strip()}
    if not versions:
        if expected == "unknown":
            return
        raise ValueError("feature_version missing for model inference")
    if versions != {expected}:
        raise ValueError(f"feature_version mismatch: expected={expected} actual={sorted(versions)}")


def _infer_single_value(df: pd.DataFrame, column: str, default: str = "") -> str:
    if column not in df.columns:
        return default
    values = [str(v) for v in df[column].dropna().astype(str).tolist() if str(v).strip()]
    unique = list(dict.fromkeys(values))
    if not unique:
        return default
    return unique[0]


def _train_range(df: pd.DataFrame) -> dict[str, str]:
    if "timestamp" not in df.columns or df.empty:
        return {"start": "", "end": ""}
    ts = pd.to_datetime(df["timestamp"], utc=True)
    return {
        "start": ts.min().isoformat(),
        "end": ts.max().isoformat(),
    }


def _precision_recall_f1(y_true: pd.Series, y_pred: pd.Series) -> tuple[float, float, float]:
    y_true_arr = y_true.astype(int)
    y_pred_arr = y_pred.astype(int)
    tp = float(((y_true_arr == 1) & (y_pred_arr == 1)).sum())
    fp = float(((y_true_arr == 0) & (y_pred_arr == 1)).sum())
    fn = float(((y_true_arr == 1) & (y_pred_arr == 0)).sum())
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def _normalize_keys(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in KEY_COLS:
        if col not in out.columns:
            raise ValueError(f"missing key column: {col}")
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    return out
