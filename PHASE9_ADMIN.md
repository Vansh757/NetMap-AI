# Phase 9: Administrator dashboard

## Roles and login

The existing `users` table has a `role` field with only `user` or `admin`. New registrations always receive the database default `user`; registration never accepts a role. `/admin/login` checks the same Werkzeug password hash as user login and also verifies the account's database role. Every admin page/API request rechecks that role in MySQL, so changing an account back to `user` takes effect immediately. Non-admin accounts receive HTTP 403 from admin pages and APIs.

Apply `migration_phase9.sql` to an existing database. Then promote an existing account deliberately (replace the username with the account to grant access to):

```sql
UPDATE users SET role = 'admin' WHERE username = 'your_existing_username';
```

Confirm one row was updated, then sign in at `/admin/login`. Do not create a shared/default admin password; the account keeps its existing hashed password. To revoke access, set its role back to `user`.

## Dashboard and privacy

The admin dashboard summarizes users, measurements, speed/latency/score, classifications, historical trends, recommendation counts, and prediction status. No password, name, email, username, account ID, or raw measurement ID is selected by the admin analytics queries.

Map and location exports group coordinates into rounded 0.001-degree cells and suppress cells with fewer than three classified measurements. Search applies to the approximate cell coordinates. Dead-zone and weak cells are classifications derived from the aggregate poor-measurement share; they are not claims about a physical cause.

Prediction statistics show only aggregate logged predictions and the Phase 7 held-out evaluation report if a model exists. Successful predictions are logged with a coarse coordinate cell and predicted class, without an account ID. Until a model is trained, the dashboard explicitly reports that prediction data is unavailable.

CSV export choices are daily aggregates, classification totals, or anonymized location cells. The project report is a downloadable text summary and contains aggregate statistics only.

## Routes

- Admin sign-in: `/admin/login`
- Dashboard: `/admin`
- Aggregate JSON API: `GET /admin/api/dashboard`
- CSV export: `GET /admin/export.csv?type=daily|classifications|locations`
- Project report: `/admin/report.txt`

All admin routes and APIs enforce a database-backed administrator role check. Filters accept optional `start_date`, `end_date`, `classification`, and (for location search) `search`; malformed dates, class values, and oversized search input are rejected.
