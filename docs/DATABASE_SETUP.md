# Database setup and schema

## Fresh installation

Create a MySQL account/database as appropriate for the local installation, then run the project schema as a MySQL administrator:

```sql
SOURCE C:/path/to/NetMap AI/schema.sql;
```

Alternatively, open `schema.sql` in MySQL Workbench and execute it. The script creates/selects `netmap_db` and creates all four current tables. Set `MYSQL_DB=netmap_db` in `.env`.

## Existing Phase 2 database

Back up the database first. Apply only migrations not already reflected by the schema, in this order:

1. `migration_phase4.sql` — location columns.
2. `migration_phase5.sql` — scoring and optional metric columns.
3. `migration_phase6.sql` — analytics indexes.
4. `migration_phase8.sql` — recommendation history table.
5. `migration_phase9.sql` — role column, admin indexes, anonymized prediction events.

Each script contains `USE netmap_db;`. Change that database name if the project uses another name. `migration_phase5.sql` modifies `jitter_ms`; check the existing table before applying to a custom schema. The base `schema.sql` describes the intended final schema but `CREATE TABLE IF NOT EXISTS` does not alter an existing table.

Confirm installation:

```sql
USE netmap_db;
SHOW TABLES;
DESCRIBE users;
DESCRIBE connectivity_measurements;
DESCRIBE connectivity_recommendations;
DESCRIBE connectivity_prediction_events;
```

## Administrator account

Register the account through the application first. Promote only the trusted account by its exact username:

```sql
USE netmap_db;
UPDATE users SET role = 'admin' WHERE username = 'YOUR_EXACT_USERNAME';
SELECT username, role FROM users WHERE username = 'YOUR_EXACT_USERNAME';
```

After verifying one row and role `admin`, sign out, then use `/admin/login`. Revoke access with:

```sql
UPDATE users SET role = 'user' WHERE username = 'YOUR_EXACT_USERNAME';
```

Avoid adding any default admin password or embedding one in source code.

## Schema reference

`schema.sql` is the canonical fresh-install schema. Auto-increment IDs and unique/index definitions are shown there. All measurements are associated with a user and are deleted with that account by the `connectivity_measurements.user_id` foreign key. Recommendations are keyed by `user_id` and a unique finding fingerprint; the current schema intentionally does not declare a foreign key for this table. Prediction events are anonymized aggregates and do not store a user ID.

| Table | Purpose | Important fields |
|---|---|---|
| `users` | Identity, login hash, role | `id`, `name`, `username`, `email`, `password`, `role`, `created_at` |
| `connectivity_measurements` | Per-test metrics, optional coordinates, score and class | `id`, `user_id`, speeds, ping/jitter/loss, browser network JSON text, latitude/longitude/accuracy, score/class/version/inputs, timestamp |
| `connectivity_recommendations` | Explainable, deduplicated finding history | `user_id`, `fingerprint`, kind, problem, recommendation, reason, severity, supporting measurement IDs, status and times |
| `connectivity_prediction_events` | Admin-level anonymous prediction totals by coarse cell | predicted poor flag, 3-decimal location cell, timestamp; no account ID |

### ER diagram description

```text
users (1) ─────── (many) connectivity_measurements
  id PK                  user_id FK → users.id

users (1) ─ ─ ─ ─ (many) connectivity_recommendations
  id PK                  user_id logical association (no declared FK)

connectivity_prediction_events
  standalone anonymized event table; no user relationship
```

One user can create many measurements. A recommendation belongs to the user whose history generated it and links to supporting measurement IDs in a serialized list. The prediction event table deliberately keeps no user identity so the administrator overview can count model outputs without retaining an account identifier.

### Nullability and meaning

- `jitter_ms`, `packet_loss_percent`, signal strength, location, accuracy, score/class and scoring audit fields can be `NULL` where unavailable/not collected.
- The current browser test does not collect packet loss or Wi-Fi signal strength; those stay unavailable, never synthetic.
- Timestamps use MySQL defaults. The API displays its server/database timestamp; document the server timezone when collecting results.
