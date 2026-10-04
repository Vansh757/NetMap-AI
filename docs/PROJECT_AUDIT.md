# Project audit (static review)

Audit basis: source, templates, JavaScript, schema/migrations, and the current repository layout were reviewed. This is a code-level review, not a security penetration test or a claim of validation on every browser, OS, database version, or deployment. The included checklist should be executed on the demonstration machine before presentation.

## Findings by requested area

| Area | Finding | Demonstration note / action |
|---|---|---|
| Authentication | Registration validates name/username/email/password and confirmation; duplicate username/email is checked and backed by DB unique keys; Werkzeug password hashing/checking is used; logout clears session. | Verify `.env` `SECRET_KEY` is set and do not expose it. No login rate limit is implemented. |
| Authorization | User routes are session-protected. Admin page/API re-reads role from DB. User history/map/prediction/recommendations are scoped by session user; deletion predicate includes owner. | Test direct access with normal account and two distinct users. A 403 for a normal user at `/admin` is expected. |
| Database queries | DB access uses `%s` placeholders and argument tuples for user-controlled values. Dynamic SQL in analytics is built from fixed predicates and validated filter choices. Inserts use parameters. | Keep placeholder values separate; never concatenate raw input into SQL. Review future routes by same standard. |
| SQL injection | No direct user-input SQL interpolation was found in reviewed endpoints. | Static review only; verify with quoted/SQL-like form/filter values and observe they are treated as data. |
| Input validation | Registration fields, map filters, coordinates, numeric measurements, browser-network keys, probe size, prediction coordinates, admin filters, and CSV type are bounded/validated. Measurement score/class are computed server-side. | Add test requests for wrong JSON type, NaN/infinity, out-of-range values, invalid dates/classes, and unmatched coordinate pairs. |
| Session security | Login clears old session before setting identity; cookies are HttpOnly and SameSite=Lax. Secret key comes from environment and startup entrypoint checks for it. | `SESSION_COOKIE_SECURE` is not set. Enable it behind HTTPS in deployment. Session is Flask's signed client-side cookie; do not store secrets in it. |
| CSRF / abuse controls | Explicit CSRF tokens and login throttling were not found. | High-priority hardening before public deployment. SameSite=Lax is defense-in-depth, not a replacement for CSRF tokens. |
| Location permission | JavaScript requests geolocation only after the user clicks; denial, timeout, unsupported API and manual selection/no-location paths are handled. Accuracy is saved when supplied. | Browser location requires permission and a secure context except trusted localhost. Verify denial path during demo. |
| Browser compatibility | Fetch/XHR, AbortController, stream reading, `crypto.getRandomValues`, Geolocation and optional Network Information API are used. Optional network hints fall back to “unavailable”. | Test current Chrome/Edge/Firefox. Network Information API and response streaming differ by browser. Some JavaScript methods may exclude older browsers. |
| API errors | Several APIs return structured 400/401/403/422/503 errors; client UI displays fetch/prediction/map failures. | DB exceptions on most page/API routes rely on Flask's generic 500 handling. Production needs monitored logs and a generic JSON error handler for APIs. |
| Empty database | Analytics/map queries return aggregate zeros/nulls/empty arrays; prediction endpoint reports no historical location data; training report has data gates. | Test truly empty schema and empty user. Empty visuals should show explanatory states. |
| Missing values | Optional jitter/coordinates/accuracy/browser hints/scoring inputs are nullable; score normalizes weights over available metrics; serializers preserve null. | Packet loss and Wi-Fi signal strength are not measured and remain unavailable. Legacy rows may lack score/class until backfilled. |
| ML failure | Missing artifact and model load/predict failures return 503; training writes a report and removes/unpublishes stale model when data gates fail; prediction confidence is null/unreported. | Joblib artifacts must be trusted. Demonstrate both “not ready” and ready flow only when artifacts and data actually exist. |
| Map loading | Map fetch handles API errors and empty points; missing heat plugin leaves marker mode available with a message. | CDN/tile network errors can still leave a blank/gray map. Test with network disconnected and ensure verbal fallback. |
| Network failures | Probe timeouts/failures are surfaced; upload has timeout; download/ping/save failures produce visible error text; progress is exposed. | Current speed test is to the application server and should be described that way. No robust retry/cancel mechanism. |
| Responsive design | Bootstrap grid and custom responsive breakpoints exist for admin, analytics, history and map layouts. | Static source review only; physically inspect common desktop, tablet and phone widths and map usability. |
| Performance | User history is bounded; maps/analytics have result limits; recommendation reads are bounded; admin exports/locations and trends have caps; common indexes exist. | Some dashboard requests issue several aggregate SQL queries. Profile with realistic volumes; pagination/rollups may be needed at scale. |
| Code organization | Scoring, ML pipeline, recommendation engine and admin analytics have separate modules; app.py still contains routes, validation, SQL, and response formatting in one large file. | For continued work, move route groups into Flask blueprints and add service/data-access modules. |
| Database consistency | Fresh schema has measurements FK; recommendations are logical `user_id` associations without FK; migration scripts target `netmap_db`; existing tables are not altered by the base `CREATE IF NOT EXISTS` schema. | Back up before migrations; verify DB name and schema before startup. Ensure signedness/types match on custom installations. |
| External resources | Leaflet/Chart.js/heat layer and OSM tile requests are external. | CDN, CSP/subresource integrity and tile-service policy need attention before a public deployment. |

## Risk priority

1. **Before public deployment:** add CSRF protection, rate-limit authentication, serve only over HTTPS, set `SESSION_COOKIE_SECURE=True`, use a production WSGI server, and keep secrets/artifacts protected.
2. **Before exam demonstration:** confirm migrations, create a controlled admin account, test both roles, and verify a working network connection for map/chart resources.
3. **For results integrity:** explain the app-server measurement endpoint and only present ML metrics from the generated report's held-out test split.

## What was not established

- No external penetration test, production load test, full end-to-end browser matrix, or independent ISP throughput validation was performed as part of this static review.
- No accuracy value or benchmark is asserted here. The presence of the training pipeline does not prove a trained model artifact exists or is useful.
- OSM/CDN behavior and geolocation are environment- and network-dependent.
