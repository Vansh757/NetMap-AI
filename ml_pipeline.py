"""Data extraction and leakage-safe feature engineering for Phase 7."""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = [
    "latitude",
    "longitude",
    "hour",
    "day_of_week",
    "previous_download_mbps",
    "previous_upload_mbps",
    "previous_latency_ms",
    "previous_connectivity_score",
    "history_download_mean_mbps",
    "history_upload_mean_mbps",
    "history_latency_mean_ms",
    "history_connectivity_score_mean",
    "history_measurement_count",
]
TARGET = "poor_connectivity"
POOR_CLASSES = {"Weak", "Dead Zone"}
CLASS_MAP = {"Excellent", "Good", "Weak", "Dead Zone"}
LOCATION_PRECISION = 3  # Approximate 100 m spatial cells, consistent with the prediction API.


def extract_measurements(connection):
    """Fetch only fields needed for modelling; never include account/profile data."""
    query = """
        SELECT id, user_id, latitude, longitude, download_mbps, upload_mbps,
               ping_ms, connectivity_score, connectivity_classification, created_at
        FROM connectivity_measurements
        WHERE connectivity_classification IS NOT NULL
        ORDER BY created_at ASC, id ASC
    """
    cursor = connection.cursor()
    try:
        cursor.execute(query)
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return pd.DataFrame(rows)


def clean_measurements(frame):
    """Normalize types, remove invalid targets/coordinates, and mark bad metrics missing."""
    data = frame.copy()
    required = {
        "user_id", "latitude", "longitude", "download_mbps", "upload_mbps",
        "ping_ms", "connectivity_score", "connectivity_classification", "created_at",
    }
    missing_columns = required.difference(data.columns)
    if missing_columns:
        raise ValueError(f"Dataset is missing required columns: {', '.join(sorted(missing_columns))}")

    # Keep MySQL's naive session timestamp clock as-is. The prediction API obtains
    # hour/day from the same MySQL session clock, keeping train/serve features aligned.
    data["created_at"] = pd.to_datetime(data["created_at"], errors="coerce", format="mixed")
    numeric = ["latitude", "longitude", "download_mbps", "upload_mbps", "ping_ms", "connectivity_score"]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
        data.loc[~np.isfinite(data[column]), column] = np.nan

    # Invalid measurements become missing; the training pipeline imputes feature values
    # using training-fold medians only. Labels and timestamps are never imputed.
    bounds = {
        "latitude": (-90, 90), "longitude": (-180, 180),
        "download_mbps": (0, 10000), "upload_mbps": (0, 10000),
        "ping_ms": (0, 60000), "connectivity_score": (0, 100),
    }
    for column, (low, high) in bounds.items():
        data.loc[~data[column].between(low, high), column] = np.nan

    data["connectivity_classification"] = data["connectivity_classification"].astype("string").str.strip()
    data = data[
        data["connectivity_classification"].isin(CLASS_MAP)
        & data["created_at"].notna()
        & data["user_id"].notna()
        & data["latitude"].notna()
        & data["longitude"].notna()
    ].copy()
    data[TARGET] = data["connectivity_classification"].isin(POOR_CLASSES).astype("int8")
    data["location_lat_cell"] = data["latitude"].round(LOCATION_PRECISION)
    data["location_lon_cell"] = data["longitude"].round(LOCATION_PRECISION)
    data["hour"] = data["created_at"].dt.hour.astype("int8")
    data["day_of_week"] = data["created_at"].dt.dayofweek.astype("int8")
    return data.sort_values(["user_id", "location_lat_cell", "location_lon_cell", "created_at", "id"])


def engineer_temporal_features(cleaned):
    """For each row, derive historical predictors using strictly earlier timestamps."""
    if cleaned.empty:
        return pd.DataFrame(columns=FEATURES + [TARGET, "created_at"])

    keys = ["user_id", "location_lat_cell", "location_lon_cell"]
    timestamp_keys = keys + ["created_at"]
    metrics = {
        "download_mbps": "download",
        "upload_mbps": "upload",
        "ping_ms": "latency",
        "connectivity_score": "connectivity_score",
    }
    # Collapse equal timestamps first so samples collected in the same second cannot
    # leak into one another through a row-wise shift.
    per_time = cleaned.groupby(timestamp_keys, as_index=False, sort=True).agg(
        **{f"_time_{name}": (source, "mean") for source, name in metrics.items()},
        **{f"_sum_{name}": (source, "sum") for source, name in metrics.items()},
        **{f"_count_{name}": (source, "count") for source, name in metrics.items()},
        _time_count=("id", "count"),
    ).sort_values(timestamp_keys)
    grouped = per_time.groupby(keys, sort=False)
    for source, name in metrics.items():
        time_col = f"_time_{name}"
        per_time[f"previous_{name}"] = grouped[time_col].shift(1)
        sum_col = f"_sum_{name}"
        count_col = f"_count_{name}"
        current_sum = per_time[sum_col].fillna(0)
        current_count = per_time[count_col].fillna(0)
        prior_sum = grouped[sum_col].cumsum() - current_sum
        prior_count = grouped[count_col].cumsum() - current_count
        per_time[f"history_{name}_mean"] = prior_sum.div(prior_count.replace(0, np.nan))

    prior_count = per_time.groupby(keys, sort=False)["_time_count"].cumsum() - per_time["_time_count"]
    per_time["history_measurement_count"] = prior_count.astype("float64")
    feature_names = {
        "previous_download": "previous_download_mbps",
        "previous_upload": "previous_upload_mbps",
        "previous_latency": "previous_latency_ms",
        "previous_connectivity_score": "previous_connectivity_score",
        "history_download_mean": "history_download_mean_mbps",
        "history_upload_mean": "history_upload_mean_mbps",
        "history_latency_mean": "history_latency_mean_ms",
        "history_connectivity_score_mean": "history_connectivity_score_mean",
    }
    per_time = per_time.rename(columns=feature_names)
    engineered = cleaned.merge(per_time[timestamp_keys + FEATURES[4:]], on=timestamp_keys, how="left", validate="many_to_one")
    return engineered[FEATURES + [TARGET, "created_at"]].sort_values("created_at").reset_index(drop=True)


def make_model_pipelines():
    """Return two comparable pipelines; imputers/scalers fit only inside each fold."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    return {
        "logistic_regression": Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(class_weight="balanced", max_iter=2000, random_state=42)),
        ]),
        "random_forest": Pipeline([
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("model", RandomForestClassifier(
                n_estimators=300, min_samples_leaf=2, class_weight="balanced_subsample",
                random_state=42, n_jobs=-1,
            )),
        ]),
    }
