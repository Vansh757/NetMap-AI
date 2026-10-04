# Phase 7: Connectivity prediction

## Current data assessment

The training run extracted 25 historical measurements. Six have coordinates and a valid class, and those six are all `Excellent`; the other 19 have no saved coordinates. A binary model for poor connectivity cannot be evaluated from one class and six eligible rows. Accordingly, the training run generated an EDA report but did not save a trained model or report fabricated metrics. The prediction API responds with HTTP 503 and the dashboard explains what data is missing until a valid model is trained.

The current report is written to `artifacts/phase7_eda_report.json` each time the training script runs.

## Target and leakage prevention

The binary target is `poor_connectivity = 1` for `Weak` or `Dead Zone`; `Excellent` and `Good` are `0`. Each sample predicts the class of that measurement. Its input features contain coordinates, hour, weekday, the prior measurement at that user/location cell, and historical averages/counts from strictly earlier timestamps at that same user/location cell. Measurements at the same timestamp are grouped before history features are calculated, preventing same-second rows from becoming one another's inputs. The current row's speed, latency, and connectivity score are outcome data and are excluded from the predictors.

Rows missing a valid target, timestamp, or location are excluded from location prediction. Invalid numeric ranges are changed to missing. Missing predictor values are median-imputed inside scikit-learn pipelines, with medians learned only from the training portion. Missing target values are never imputed.

## Training and model selection

Run from the project directory after collecting more varied, location-enabled measurements:

```text
python train_model.py
```

The script extracts only measurement fields (no account names or email addresses), creates an EDA summary, and uses a chronological 60/20/20 train/validation/test split. Logistic Regression and Random Forest pipelines are compared on validation balanced accuracy, then F1 and average precision as tie-breakers. The selected pipeline is evaluated once on the later held-out test period and saved to `artifacts/phase7_connectivity.joblib`. It requires at least 100 eligible rows, both target classes in every split, at least 20 training examples per class, and at least 5 validation/test examples per class. Those are minimum safeguards, not a claim that 100 rows are sufficient for a reliable production model.

Only when training succeeds does the EDA report include measured validation and test metrics. The application displays held-out metrics from that report. Prediction confidence is not shown: classifier probabilities have not been calibrated.

## Prediction API and UI

- Authenticated page: `/predictions`
- Authenticated endpoint: `POST /api/predictions/connectivity`
- Request JSON: `{"latitude": 37.0, "longitude": -122.0}`
- The API uses the signed-in user's prior measurements in the selected approximate 0.001-degree location cell. It returns the predicted poor/not-poor status and prior sample count, but no probability.
- The main dashboard links to the prediction page. When no trained artifact exists, the page shows the data assessment and instructions to collect more measurements and rerun training.

The prediction target depends on the coverage and quality of stored browser measurements, including user-permitted location data. Sparse, unbalanced data can produce weak or geographically biased predictions. A prediction is an exploratory estimate, not a guarantee of future internet service.
