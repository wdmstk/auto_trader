from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from lightgbm import LGBMClassifier


@dataclass(frozen=True)
class ModelArtifacts:
    model: LGBMClassifier
    threshold: float
    metrics: dict[str, float]


def train_binary_classifier(
    *,
    dataset: pd.DataFrame,
    feature_columns: list[str],
) -> ModelArtifacts:
    train = dataset[dataset["split"] == "train"]
    valid = dataset[dataset["split"] == "valid"]
    if train.empty or valid.empty:
        raise ValueError("train/valid split must not be empty")

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
    metrics = {"valid_accuracy": acc, "threshold": threshold}
    return ModelArtifacts(model=model, threshold=threshold, metrics=metrics)


def optimize_threshold(y_true: pd.Series, score: pd.Series) -> float:
    best_t = 0.5
    best_acc = -1.0
    for i in range(20, 81):
        t = i / 100.0
        pred = (score >= t).astype(int)
        acc = float((pred == y_true).mean())
        if acc > best_acc:
            best_acc = acc
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
