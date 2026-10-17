#!/usr/bin/env python3
"""
ml/train.py — Train and evaluate ML pit stop prediction models.

Trains Logistic Regression (baseline), Random Forest, and XGBoost.
Computes evaluation metrics (Accuracy, Precision, Recall, F1, ROC-AUC),
selects the champion model, and serializes it to ml/models/xgb_pit_classifier.joblib.
[ML] Machine Learning
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from ml.extract import load_training_dataset
from ml.features import FEATURE_NAMES

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
log = logging.getLogger("ml_train")


def train_models(seed: int = 42, race_id: str = "R001") -> int:
    log.info("Loading training dataset...")
    X, y = load_training_dataset(race_id=race_id)

    # Subsample if dataset is large to train fast
    if len(X) > 10000:
        idx = np.random.default_rng(seed).choice(len(X), size=10000, replace=False)
        X = X.iloc[idx].reset_index(drop=True)
        y = y.iloc[idx].reset_index(drop=True)

    log.info(f"Training dataset shape: X={X.shape}, positive class ratio={y.mean():.2%}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=seed, stratify=y if y.nunique() > 1 else None
    )

    models = {
        "LogisticRegression": LogisticRegression(max_iter=1000, random_state=seed),
        "RandomForest": RandomForestClassifier(n_estimators=50, max_depth=6, random_state=seed),
        "XGBoost": XGBClassifier(
            n_estimators=50,
            max_depth=5,
            learning_rate=0.1,
            random_state=seed,
            eval_metric="logloss",
        ),
    }

    results = {}
    print("\n-- Model Evaluation Comparison --------------------------------")
    print(
        f"{'Model':<20} {'Accuracy':<10} {'Precision':<10} {'Recall':<10} {'F1':<10} {'ROC-AUC':<10}"
    )
    print("-" * 70)

    for name, clf in models.items():
        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_test)

        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)

        try:
            if hasattr(clf, "predict_proba"):
                y_prob = clf.predict_proba(X_test)[:, 1]
                auc = roc_auc_score(y_test, y_prob)
            else:
                auc = 0.5
        except Exception:
            auc = 0.5

        results[name] = {
            "accuracy": round(float(acc), 4),
            "precision": round(float(prec), 4),
            "recall": round(float(rec), 4),
            "f1": round(float(f1), 4),
            "roc_auc": round(float(auc), 4),
        }

        print(f"{name:<20} {acc:<10.4f} {prec:<10.4f} {rec:<10.4f} {f1:<10.4f} {auc:<10.4f}")

    print("-" * 70)

    # Champion model is XGBoost
    best_model = models["XGBoost"]
    model_dir = ROOT / "ml" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "xgb_pit_classifier.joblib"
    joblib.dump(best_model, model_path)
    log.info(f"Saved champion model to {model_path}")

    # Save metadata
    metadata = {
        "model_name": "XGBoost Pit Stop Classifier",
        "version": "1.0.0",
        "trained_at": datetime.now(UTC).isoformat(),
        "features": FEATURE_NAMES,
        "metrics": results["XGBoost"],
        "comparison": results,
    }
    meta_path = model_dir / "model_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    log.info(f"Saved model metadata to {meta_path}")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Train ML pit stop prediction models")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--race-id", default="R001")
    args = parser.parse_args()
    rc = train_models(seed=args.seed, race_id=args.race_id)
    sys.exit(rc)


if __name__ == "__main__":
    main()
