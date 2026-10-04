# Project architecture

## Request and data flow

```text
Browser (Jinja pages + static JavaScript)
  ├─ Auth forms / session cookie
  ├─ Connectivity probes → Flask probe endpoints
  ├─ Optional geolocation permission/manual Leaflet point
  └─ Chart.js / Leaflet requests → Flask JSON endpoints
                                         │
                                         ├─ scoring.py + scoring_config.py
                                         ├─ recommendation_engine.py
                                         ├─ admin_analytics.py
                                         ├─ ml_pipeline.py (shared features)
                                         └─ MySQL (parameterized queries)

train_model.py → MySQL measurements → clean/EDA/features → chronological
                 validation/test → joblib model + JSON report in artifacts/
```

## Main components

- `app.py`: Flask app factory-equivalent configuration, session/role decorators, HTML routes, JSON APIs, validation, SQL interactions, and response handling.
- `templates/`: Jinja views for public/auth pages, user dashboard, measurement forms/history, map, analytics, prediction, recommendations, and admin dashboard.
- `static/js/main.js`: browser-side test flow, permission-requested location, map retrieval/filters, and map charts.
- `static/js/analytics.js`, `prediction.js`, `admin.js`: analytics, prediction UI, and administrator visualizations.
- `scoring_config.py` and `scoring.py`: centralized metric curves, weights, thresholds, and transparent scoring.
- `recommendation_engine.py`: bounded analysis of a user's recent history, reasons/evidence, deduplication and lifecycle.
- `admin_analytics.py`: validated admin filters, anonymized summaries, chart data and CSV source rows.
- `ml_pipeline.py`, `train_model.py`: data extraction, cleaning, temporal feature engineering, model comparison, chronological evaluation and artifact writing.
- `schema.sql`, `migration_phase*.sql`: fresh schema and upgrades for existing database installations.
- `artifacts/`: generated model and training report (ignored by Git; regenerate locally).

## Core data flow

1. Browser requests a test only after a user click. Geolocation is requested only when the user selects the location action; denial does not block a test.
2. Browser measures HTTP timing and transfer throughput between itself and the Flask server, gathers browser-exposed network hints, and sends a validated request.
3. Flask validates values, calculates the score/class, inserts the row with the authenticated user ID, and commits to MySQL.
4. User map, history and analytics queries filter by `session['user_id']`; deletes include both measurement ID and owner ID.
5. Recommendation refresh evaluates bounded recent user rows and upserts explainable evidence with stable fingerprints.
6. Model training is offline/manual. The prediction endpoint uses the installed artifact and user's prior measurements for approximate location features. It emits no calibrated confidence.
7. Admin dashboard performs aggregate queries. It excludes identity fields and coarsens/suppresses location cells.

## Trust boundaries

The browser is untrusted: never accept its user ID, score, classification, SQL fragments or arbitrary network fields as authoritative. The Flask secret signs the session cookie; MySQL enforces unique identity constraints and parameterized query values. The serialized scikit-learn joblib file must be generated and controlled by the project owner because loading a malicious joblib artifact can execute code. The UI depends on external CDN libraries and OpenStreetMap tile service availability.
