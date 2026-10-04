"""Extract, analyze, and train the Phase 7 next-measurement classifier."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import MySQLdb
import MySQLdb.cursors
import numpy as np
from dotenv import load_dotenv
from joblib import dump
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from ml_pipeline import FEATURES, TARGET, clean_measurements, engineer_temporal_features, extract_measurements, make_model_pipelines

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
REPORT_PATH = ARTIFACTS / "phase7_eda_report.json"
MODEL_PATH = ARTIFACTS / "phase7_connectivity.joblib"
MINIMUM_ROWS = 100
MINIMUM_TRAIN_CLASS = 20
MINIMUM_EVAL_CLASS = 5


def _class_counts(labels):
    counts = labels.value_counts().to_dict()
    return {"not_poor": int(counts.get(0, 0)), "poor": int(counts.get(1, 0))}


def _time_split(data):
    timestamps = np.array(sorted(data["created_at"].dropna().unique()))
    if len(timestamps) < 10:
        return None
    train_cut = timestamps[max(0, int(len(timestamps) * 0.60) - 1)]
    validation_cut = timestamps[max(0, int(len(timestamps) * 0.80) - 1)]
    train = data[data["created_at"] <= train_cut]
    validation = data[(data["created_at"] > train_cut) & (data["created_at"] <= validation_cut)]
    test = data[data["created_at"] > validation_cut]
    return train, validation, test


def _metrics(model, x, y):
    predicted = model.predict(x)
    values = {
        "accuracy": float(accuracy_score(y, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(y, predicted)),
        "precision": float(precision_score(y, predicted, zero_division=0)),
        "recall": float(recall_score(y, predicted, zero_division=0)),
        "f1": float(f1_score(y, predicted, zero_division=0)),
    }
    # Ranking metrics are for model comparison only; the application does not expose
    # uncalibrated classifier outputs as a confidence/probability.
    if hasattr(model, "predict_proba"):
        scores = model.predict_proba(x)[:, 1]
    elif hasattr(model, "decision_function"):
        scores = model.decision_function(x)
    else:
        scores = None
    if scores is not None and y.nunique() == 2:
        values["roc_auc"] = float(roc_auc_score(y, scores))
        values["average_precision"] = float(average_precision_score(y, scores))
    else:
        values["roc_auc"] = None
        values["average_precision"] = None
    return values


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")


def main():
    load_dotenv(ROOT / ".env")
    connection = MySQLdb.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", "root"),
        passwd=os.getenv("MYSQL_PASSWORD", ""),
        db=os.getenv("MYSQL_DB", "netmap_db"),
        charset="utf8mb4",
        cursorclass=MySQLdb.cursors.DictCursor,
    )
    try:
        raw = extract_measurements(connection)
    finally:
        connection.close()

    original_classes = raw.get("connectivity_classification", []).value_counts(dropna=False).to_dict() if not raw.empty else {}
    raw_timestamps = __import__("pandas").to_datetime(raw["created_at"], errors="coerce", format="mixed") if not raw.empty else None
    cleaned = clean_measurements(raw)
    data = engineer_temporal_features(cleaned)
    eda = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_rows": int(len(raw)),
        "rows_with_valid_target_and_coordinates": int(len(cleaned)),
        "engineered_rows": int(len(data)),
        "distinct_users_in_source": int(raw["user_id"].nunique()) if not raw.empty else 0,
        "distinct_spatial_cells": int(cleaned[["location_lat_cell", "location_lon_cell"]].drop_duplicates().shape[0]) if not cleaned.empty else 0,
        "first_timestamp": raw_timestamps.min().isoformat() if raw_timestamps is not None and raw_timestamps.notna().any() else None,
        "last_timestamp": raw_timestamps.max().isoformat() if raw_timestamps is not None and raw_timestamps.notna().any() else None,
        "classification_counts": {str(k): int(v) for k, v in original_classes.items()},
        "target_counts_after_cleaning": _class_counts(data[TARGET]) if not data.empty else {"not_poor": 0, "poor": 0},
        "missing_percent_before_cleaning": {
            column: round(float(raw[column].isna().mean() * 100), 2)
            for column in ["latitude", "longitude", "download_mbps", "upload_mbps", "ping_ms", "connectivity_score"]
            if column in raw
        },
        "feature_missing_percent_after_engineering": {
            column: round(float(data[column].isna().mean() * 100), 2) if len(data) else None
            for column in FEATURES if column in data
        },
        "target_definition": "Poor = Weak or Dead Zone; outcome is the current row and predictor metrics come only from strictly earlier measurements at the same user/location cell.",
        "feature_columns": FEATURES,
        "training_status": "not_trained",
        "training_reason": None,
        "validation_metrics": {},
        "test_metrics": {},
        "selected_model": None,
    }

    split = _time_split(data)
    reason = None
    if len(data) < MINIMUM_ROWS:
        reason = f"Only {len(data)} eligible location measurements are available; at least {MINIMUM_ROWS} are required before model evaluation."
    elif split is None:
        reason = "There are too few distinct timestamps for a chronological train, validation, and test split."
    else:
        train, validation, test = split
        if min(_class_counts(train[TARGET]).values()) < MINIMUM_TRAIN_CLASS:
            reason = f"The training period needs at least {MINIMUM_TRAIN_CLASS} examples of each target class."
        elif any(y[TARGET].nunique() < 2 or min(_class_counts(y[TARGET]).values()) < MINIMUM_EVAL_CLASS for y in (validation, test)):
            reason = f"Validation and test periods each need at least {MINIMUM_EVAL_CLASS} examples of both classes."

    if reason:
        eda["training_reason"] = reason
        _write_json(REPORT_PATH, eda)
        print(json.dumps(eda, indent=2))
        print(f"\nModel not trained: {reason}")
        return

    x_train, y_train = train[FEATURES], train[TARGET]
    x_validation, y_validation = validation[FEATURES], validation[TARGET]
    x_test, y_test = test[FEATURES], test[TARGET]
    candidate_results = {}
    fitted_candidates = {}
    for name, pipeline in make_model_pipelines().items():
        pipeline.fit(x_train, y_train)
        validation_metrics = _metrics(pipeline, x_validation, y_validation)
        candidate_results[name] = validation_metrics
        fitted_candidates[name] = pipeline

    # Model selection uses validation performance only. The chronological test period
    # remains untouched until the winner is chosen.
    winner = max(
        candidate_results,
        key=lambda name: (
            candidate_results[name]["balanced_accuracy"],
            candidate_results[name]["f1"],
            candidate_results[name]["average_precision"] or 0,
        ),
    )
    selected = make_model_pipelines()[winner]
    combined_train_validation = __import__("pandas").concat([train, validation], ignore_index=True)
    selected.fit(combined_train_validation[FEATURES], combined_train_validation[TARGET])
    test_metrics = _metrics(selected, x_test, y_test)
    artifact = {
        "pipeline": selected,
        "features": FEATURES,
        "target_definition": "Poor = Weak or Dead Zone at the next measurement.",
        "selected_model": winner,
        "validation_metrics": candidate_results,
        "test_metrics": test_metrics,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "training_rows": int(len(combined_train_validation)),
        "test_rows": int(len(test)),
        "location_precision": 3,
        "probabilities_calibrated": False,
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    dump(artifact, MODEL_PATH)
    eda.update({
        "training_status": "trained",
        "selected_model": winner,
        "validation_metrics": candidate_results,
        "test_metrics": test_metrics,
        "training_rows": int(len(combined_train_validation)),
        "test_rows": int(len(test)),
        "training_reason": None,
    })
    _write_json(REPORT_PATH, eda)
    print(json.dumps(eda, indent=2))
    print(f"\nSelected from measured validation results: {winner}")
    print(f"Held-out chronological test metrics: {json.dumps(test_metrics, sort_keys=True)}")
    print(f"Saved model: {MODEL_PATH}")


if __name__ == "__main__":
    main()
