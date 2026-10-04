# Phase 8: Recommendation engine

## What it analyzes

The engine reads at most 1,000 measurements per signed-in user from the prior 60 days. It generates recommendations only from stored measurement classifications, scores, timestamps, and permitted coordinates. The current data has no poor classifications, so no recommendation is expected until the user has qualifying evidence.

- **Repeated location:** at least five recent readings in a rounded 0.001-degree location cell, with at least 40% classified Weak or Dead Zone. Severity is Information below 60%, Attention from 60%, and Critical at 80% with at least eight poor readings.
- **Time period:** at least five readings in one of four six-hour periods, a poor rate of at least 40%, and at least 15 percentage points above the user's overall recent poor rate. Higher rates receive higher severity.
- **Nearby cluster:** at least three poor readings across at least two spatial cells within approximately 500 metres. This identifies a measured cluster; it does not infer the physical cause.
- **Abnormal result:** a current score at least 15 points, or three robust median deviations, below the prior location baseline. At least eight preceding scored readings are required.

The system does not assert that a router, access point, provider, or obstruction caused an issue. Suggested coverage/access-point checks explicitly state that the measurements do not identify the physical cause.

## Persistence and history

`connectivity_recommendations` stores the user, stable detector fingerprint, severity, title, problem, suggested action, evidence reason, up to 20 supporting measurement IDs, and first/last-seen timestamps. A unique user/fingerprint index prevents duplicate active recommendations. When a pattern disappears, its recommendation is marked resolved. If it returns after resolution, a new episode is recorded so history retains the prior resolved event.

The recommendation engine is isolated in `recommendation_engine.py`; a future prediction detector can add another evidence source without changing ownership checks or persistence. Current recommendations are based only on measurements.

## Routes

- Dashboard displays the five highest severity active recommendations and links to evidence.
- `/recommendations` shows active and resolved history.
- `GET /api/recommendations` returns the signed-in user's active items; `?history=1` returns history.
- `POST /api/recommendations/refresh` reevaluates recent measurements.
- Evidence links open the matching measurement, with ownership enforced by the measurement history query.

## Database setup

For an existing installation, run `migration_phase8.sql` once against `netmap_db`. New installations get the table from `schema.sql`. The migration uses a signed integer for recommendation `user_id` so it also works with the existing database's signed `users.id`; the application always scopes reads and writes to the authenticated session user ID.
