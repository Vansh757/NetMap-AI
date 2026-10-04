# Testing checklist and sample cases

Use a local/test database with synthetic accounts and non-sensitive measurements. Do not test destructive operations on the only copy of project data. This document is a manual checklist, not a report that these cases have already passed.

## Pre-demo checklist

- [ ] `.env` has a private `SECRET_KEY` and correct MySQL settings; `.env` is not staged/committed.
- [ ] MySQL is running; all expected tables/columns/indexes exist after schema or migration setup.
- [ ] App starts with `python app.py`; homepage and login/register pages load.
- [ ] Register one normal user and one separately controlled admin account; verify no password is stored in plain text.
- [ ] Normal user cannot access `/admin`; administrator can use `/admin/login` and dashboard.
- [ ] Location prompt appears only after user action; denial and manual-location paths work.
- [ ] Run one test; confirm timestamp, speeds, latency, score/class and optional location appear in MySQL/history.
- [ ] Confirm no packet loss/signal value is fabricated; network hints display unavailable where unsupported.
- [ ] History/map/analytics work with one record and with no records; filters have useful empty states.
- [ ] Delete own measurement; another account cannot delete/view it by changing the ID.
- [ ] Prediction page clearly reports not-ready when model is missing; if ready, verify its status against a generated report.
- [ ] Recommendation reason links open supporting rows; no recommendation claims an exact physical cause.
- [ ] Admin map suppresses cells below threshold; no account names/emails/IDs/passwords appear in response or exports.
- [ ] Check desktop and phone layouts; verify external map/chart resources load.
- [ ] Have screenshots/backup path and a verbal explanation of measurement and ML limitations ready.

## Sample test cases

| ID | Scenario / steps | Expected result |
|---|---|---|
| AUTH-01 | Register valid name, username, email, matching 8+ character password. | Account is created, password is a Werkzeug hash, success message shown, user can log in. |
| AUTH-02 | Register using existing username or email. | No second account; duplicate message; unique DB constraint remains effective. |
| AUTH-03 | Submit invalid email, short password, mismatched confirmation, invalid username. | Validation errors shown; no database row created. |
| AUTH-04 | Open `/dashboard` in private/incognito session. | Redirect to login; after login returns to an allowed local page. |
| AUTH-05 | POST `/logout` as signed-in user. | Session cleared and user redirected to login; protected page requires sign-in again. |
| AUTHZ-01 | Sign in as `user`, request `/admin` and `/admin/api/dashboard`. | Page denied (403); API denied (403); no admin data returned. |
| AUTHZ-02 | User A attempts to open/delete a known User B measurement ID. | No User B record or data exposed; delete reports not found/no change. |
| SQL-01 | Use quotes and SQL-like strings in username, search and filter values. | Treated as ordinary input or rejected by validation; query remains intact. |
| LOC-01 | Click current-location button and grant permission. | Coordinates and browser accuracy displayed and attached to the saved test. |
| LOC-02 | Deny location or use unsupported browser. | Clear message; manual point or test without location remains available. |
| MEAS-01 | Run a normal measurement with GPS unavailable. | Speeds/ping are displayed and persisted; coordinates null; score calculated from available values. |
| MEAS-02 | POST boolean, string, NaN-like, negative or excessively large metric. | `400`; no measurement inserted. |
| MEAS-03 | Supply only latitude, out-of-range coordinates, invalid accuracy or unsupported network key. | `400`; no row inserted. |
| EMPTY-01 | Use empty test DB/user and open history, map, analytics, admin stats. | Empty-state UI and zero/null aggregates; no unhandled client error. |
| MAP-01 | Filter by valid dates/classification, then invalid date or reversed range. | Valid filter shows only matching user rows; invalid filter receives clear `400`. |
| MAP-02 | Block CDN/tile connection or heat script. | Error/fallback is understandable; map failure does not imply data exists or fabricate map points. |
| ML-01 | Remove/move model artifact in a development copy and request prediction. | `503` and not-ready UI; no confidence is shown. Restore artifact after case. |
| ML-02 | Predict with malformed/out-of-range coordinate and with no prior location history. | `400` for invalid input; `422` for missing history. |
| REC-01 | Use sparse history, then repeated poor readings at one approximate location. | No unsupported warning from sparse data; repeated case includes numerator/denominator and evidence links. |
| ADMIN-01 | Filter admin dashboard and download each CSV type/report as admin. | Output follows filters, contains aggregates only, and suppresses location cells below threshold. |
| ADMIN-02 | Open admin endpoints unauthenticated. | Page redirects to admin login; APIs return 401. |
| RESP-01 | Inspect at ~375px, tablet width, and desktop. | Forms/cards/charts fit; map remains usable; no horizontal overflow. |

## Suggested database checks

```sql
SELECT id, username, role, created_at FROM users;
SELECT id, user_id, download_mbps, upload_mbps, ping_ms, jitter_ms,
       packet_loss_percent, latitude, longitude, connectivity_score,
       connectivity_classification, created_at
FROM connectivity_measurements ORDER BY id DESC LIMIT 10;
SELECT COUNT(*) FROM connectivity_prediction_events;
```

Do not query/select password hashes for a presentation screenshot. A password hash is still sensitive account data.
