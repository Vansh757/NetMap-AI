# API documentation

All routes are served by the Flask app. Except for public pages and login/registration, APIs require the Flask session cookie. JSON endpoints return JSON errors with a 4xx/5xx status where handled. User data endpoints are scoped to the current session account. Admin APIs require the database role `admin`.

## User connectivity APIs

| Method / path | Auth | Purpose / inputs | Success |
|---|---|---|---|
| `GET /api/connectivity/ping` | User | No input; uncached HTTP round-trip probe to this app | `200 text/plain` |
| `GET /api/connectivity/download?bytes=N` | User | `N` integer 1–4,194,304; download probe from this app | Binary body |
| `POST /api/connectivity/upload` | User | Raw 1 byte–4 MiB body, `Content-Type: application/octet-stream` | `200 text/plain` |
| `POST /api/measurements` | User | JSON of speed/ping values, nullable jitter, optional paired coordinates/accuracy, allowed browser-network keys | `201` with ID, timestamp, score/class and optional location |
| `GET /api/measurements/map` | User | Optional `start_date`, `end_date` (`YYYY-MM-DD`), `classification` | Current user's map points, summary, timeline, class totals |
| `GET /api/analytics` | User | Optional date/classification/location filters | Summary, trends, time/day groups, locations, historical comparison |
| `POST /api/predictions/connectivity` | User | JSON `{ "latitude": number, "longitude": number }` | Prediction label; 503 if no loadable trained model, 422 if no history at selected area, 400 for invalid coordinates |
| `GET /api/recommendations` | User | Optional `history=1` | Current-user recommendation records and supporting links |
| `POST /api/recommendations/refresh` | User | No body | Recomputed current-user findings |

`POST /api/measurements` requires `download_mbps`, `upload_mbps`, and `ping_ms` as finite JSON numbers within the server bounds. Coordinates must be supplied together. Browser network values are allow-listed. The server calculates score/class itself rather than trusting a client-submitted score.

## Administrator APIs

| Method / path | Auth | Purpose / inputs |
|---|---|---|
| `GET /admin/api/dashboard` | Admin | Optional validated date, class and location search filters; anonymized aggregate JSON |
| `GET /admin/export.csv?type=daily` | Admin | CSV daily aggregates; `type` may be `daily`, `classifications`, or `locations` |
| `GET /admin/report.txt` | Admin | Filtered text project summary |

Location-cell admin data is rounded and suppressed below the implementation's minimum sample count. APIs omit user profile and account identifiers. The user map is private to the signed-in user's measurements and is not the admin aggregate map.

## Other routes

- Public: `GET /`, `/about`, `/contact`; `GET/POST /register`, `/login`, `/admin/login`.
- Authenticated pages: `/dashboard`, `/profile`, `/connectivity-test`, `/measurements`, `/map`, `/analytics`, `/predictions`, `/recommendations`.
- User-owned mutation: `POST /measurements/<measurement_id>/delete`.
- Logout: `POST /logout`.
- Admin page: `GET /admin`.

## Authentication/error behavior

- Unauthenticated page routes redirect to login; unauthenticated JSON APIs return `401` where their decorators are used.
- Non-admin admin pages return `403`; non-admin admin API calls return `403`.
- Invalid filters/measurement input return `400`; a prediction request without enough prior location data returns `422`; missing/unusable model returns `503`.
- Database connectivity failures may use Flask's generic error response; check server logs for local debugging. Do not enable debug mode on a public host.

## Example requests

Use a browser session cookie obtained by signing in; examples are illustrative and do not include credentials:

```http
POST /api/measurements
Content-Type: application/json

{
  "download_mbps": 34.2,
  "upload_mbps": 8.1,
  "ping_ms": 42.5,
  "jitter_ms": 3.8,
  "browser_network": {"online": true},
  "latitude": null,
  "longitude": null,
  "location_accuracy_m": null
}
```

The API calculates the stored connectivity score and classification. The example numbers are only request-format examples, not project results.
