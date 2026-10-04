# Project overview for demonstration

## Problem statement

Users need a way to record connectivity performance at different times and opt-in locations, compare observations over time, and identify recurring poor-connectivity patterns. Individual speed readings can be noisy and do not alone establish the cause of a network problem.

## Project objectives

1. Provide registered users with authenticated access to a personal connectivity dashboard.
2. Measure browser-to-application-server HTTP latency and transfer throughput where the browser can observe them.
3. Persist measurements with timestamps, optional permission-based location and browser network hints.
4. Summarize performance through a configurable multi-metric connectivity score and class.
5. Map and filter measurements while keeping user records private.
6. Present historical statistics and trends.
7. Evaluate an optional poor-connectivity classifier from historical data without fabricating metrics or model results.
8. Generate transparent recommendations with supporting measurements and reasons.
9. Provide administrators with role-protected, anonymized aggregate views and exports.

## Existing system and proposed system

**Existing approach:** browser/network checks often show an isolated speed result, depend on the measurement server, and may not connect readings to location, timestamp, historical trends, or evidence-backed follow-up. This is a general comparison, not a claim about every existing product.

**Proposed system:** NetMap AI combines account-scoped measurement history, user-permitted location mapping, a configurable score, charts, a data-gated historical prediction pipeline, explainable recommendations, and an aggregate admin dashboard in one Flask/MySQL application.

## Advantages

- Results are timestamped and associated with the authenticated account.
- Location is optional and captured only after an explicit browser permission action; manual selection is available.
- The score records which available metric inputs were used; unavailable packet-loss and signal metrics are not invented.
- User endpoints constrain reads/deletes to the owner.
- Admin dashboard excludes direct account identifiers and coarsens/suppresses map cells.
- Recommendation text includes evidence and cautions against asserting physical causes.
- Model training uses time-ordered evaluation and refuses to publish a model when minimum data gates fail.

## Modules

1. Authentication/profile and role authorization.
2. Connectivity test and measurement persistence.
3. Location permission and manual selection.
4. User measurement map and history.
5. Connectivity scoring and classification.
6. Analytics dashboard and filtering.
7. Historical ML training and prediction UI/API.
8. Explainable recommendation engine and history.
9. Administrator aggregate dashboard/export/report.

## Technologies

- Python, Flask, Jinja2, Werkzeug security utilities.
- MySQL with `Flask-MySQLdb` / `mysqlclient` and parameterized SQL.
- JavaScript Fetch/XHR, browser Geolocation API, optional Network Information API.
- Leaflet.js, OpenStreetMap tiles, Leaflet.heat, Chart.js.
- Pandas, NumPy, scikit-learn and joblib for offline model training/serving.
- `python-dotenv` for local environment configuration.

## Specific innovation

The project-specific contribution is the implemented combination of browser-to-app measurement, permission-based measurement mapping, history and analytics, an optional historical poor-connectivity prediction pipeline, and explainable recommendations linked to observed data. It is a practical integration and workflow contribution, not a claim of global uniqueness or a new measurement protocol.

## Results to present

The live application can demonstrate saved measurements, user-scoped history, optional map points, computed score/class, analytics, recommendation evidence, admin aggregates, and (only if a valid artifact exists) model predictions. Report actual values from the demonstration database and the generated Phase 7 evaluation report. Do not insert illustrative numbers from documentation as experimental results. If the model is not trained, report that honestly and show its training status as not ready.

## Known limitations

- Throughput and latency are measured between the browser and this Flask application server. They are not a controlled ISP-wide test and depend on server location/load, hosting, TLS/proxy behavior, device and browser.
- The latency probes are HTTP round trips; they are not ICMP ping. Jitter is the mean absolute difference between consecutive successful HTTP probe timings in a short run, not a standardized network jitter test. Failed probes are shown in progress messaging; packet loss is not calculated.
- Browser network hints vary by browser and may be estimates or unavailable. Browser JavaScript does not expose Wi-Fi RSSI/signal strength in a portable way.
- Geolocation accuracy depends on device/browser and user permission. Manual map selection has no accuracy measurement. Coordinates can reveal sensitive places; user maps are account-scoped, but database access still requires care.
- Classification is based on chosen score weights and curves; it is a project-defined indicator, not a carrier SLA.
- Recommendations indicate observed patterns, not proven physical causes. Sparse history may prevent them from appearing.
- The ML target is derived from the system's own Weak/Dead Zone classes, so prediction measures pattern repetition under the project's class definition. Small, biased, or geographically narrow data limits generalization. Probabilities are not presented as confidence.
- Leaflet/Chart.js/heat layer and OpenStreetMap tiles load from external services/CDNs; offline or blocked access can prevent visuals. OpenStreetMap tile usage must follow its tile policy for deployment.
- Current code does not include CSRF tokens or login rate limiting. Flask's client-side session cookie is signed, not server-side; HTTPS and secure cookie settings are required for deployment.
- The repository uses Flask's development server when launched with `python app.py`; production hosting needs a suitable WSGI server and HTTPS reverse proxy.

## Future scope

- Add CSRF protection to all state-changing form/API requests and login throttling/account lockout controls.
- Configure production HTTPS, secure cookie flags, centralized secret management, structured logging and deployment WSGI server.
- Use a neutral, well-provisioned measurement endpoint and repeated/cancellable probes; define a standardized methodology and report server-side confounders.
- Add opt-in data retention/export/deletion policies and location minimization controls.
- Gather broader, balanced labeled datasets and evaluate by spatial/user/time holdout; calibrate probabilities only with adequate data.
- Add robust monitoring, automated migration management, CI checks, and integration tests with a disposable test database.
- Add device-side signal measurements only through a platform that explicitly exposes them, with clear provenance and permission.
