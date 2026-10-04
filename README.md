# NetMap AI

NetMap AI is a Flask and MySQL web application for measuring application-server connectivity, saving user-owned results, mapping opted-in measurement locations, summarizing historical performance, trying a data-gated poor-connectivity classifier, and presenting evidence-based recommendations.

This repository contains the continuing project implementation (Phases 2–9). It is a university demonstration/research prototype. Measurements, predictions, and recommendation output should be presented with their limitations; see [Known limitations](docs/PROJECT_OVERVIEW.md#known-limitations).

## Features currently implemented

- Account registration/login/logout with Werkzeug password hashes and role-aware administrator access.
- Authenticated connectivity probes, measurement history, profile, deletion, map, and analytics views.
- Location capture only after browser permission, plus optional manual map selection.
- Transparent weighted scoring in `scoring_config.py` / `scoring.py`.
- MySQL-backed recommendation history with supporting measurement links.
- Optional Phase 7 model training/evaluation and an authenticated prediction endpoint. A model is not guaranteed to exist; training is deliberately data-gated.
- Aggregate administrator dashboard, privacy-coarsened location cells, filters, CSV exports, and text report.

## Quick start (Windows PowerShell)

Prerequisites: Python 3.10+ (the project uses `zoneinfo` and current pandas/sklearn APIs), MySQL 8.0+, and a modern browser. Use MySQL Workbench or the MySQL command line.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with local MySQL credentials and a long random `SECRET_KEY`. Do not commit `.env`.

For a new database, run `schema.sql`. For an existing Phase 2 database, apply only the missing migrations in order: `migration_phase4.sql`, `migration_phase5.sql`, `migration_phase6.sql`, `migration_phase8.sql`, and `migration_phase9.sql`. See [Database setup](docs/DATABASE_SETUP.md).

```powershell
python app.py
```

Open `http://127.0.0.1:5000`. Flask's development server is for local demonstration only. See [Installation](docs/INSTALLATION.md) for full instructions and administrator role setup.

## Documentation

- [Installation guide](docs/INSTALLATION.md)
- [Database setup and schema](docs/DATABASE_SETUP.md)
- [API documentation](docs/API.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Project objectives, modules, results, limitations, and future scope](docs/PROJECT_OVERVIEW.md)
- [Audit findings and demonstration checklist](docs/PROJECT_AUDIT.md)
- [Testing checklist and sample test cases](docs/TESTING.md)
- [Connectivity score formula](PHASE5_SCORING.md)
- [Machine-learning pipeline](PHASE7_ML.md)
- [Recommendations](PHASE8_RECOMMENDATIONS.md)
- [Administrator dashboard](PHASE9_ADMIN.md)

## Current audit summary

Static review found parameterized SQL for user-controlled query values, password hashing, role checks against the database on administrator routes, and ownership predicates on user measurement reads/deletes. Location access is initiated from a user action and the map/API return no account profile fields. Empty model and empty-query states have UI/API handling. Important demonstration caveats remain: explicit CSRF tokens and login throttling are absent; production HTTPS cookie settings must be enabled; speed values are measured against this Flask app; and browser GPS/network APIs and external map/chart CDNs can be unavailable. Details and test cases are in [Project audit](docs/PROJECT_AUDIT.md).

## Research integrity

Do not report model accuracy unless a current training report exists and its held-out metrics are shown. Do not describe a recommendation as proof of a physical cause. The implementation's innovation is its combination of application-server measurement, permission-based mapping, analytics, an optional history-based classifier, and evidence-linked recommendations—not a claim that no similar system exists.

Author 

Vansh Patel