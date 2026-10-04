# Installation guide

## Requirements

- Windows 10/11 or another OS that supports Python and MySQL.
- Python 3.10 or newer recommended.
- MySQL Server 8.0 or newer and an account that can create/alter the project database.
- Browser with JavaScript enabled. Geolocation generally requires a secure context; `localhost`/`127.0.0.1` is treated as a trusted local context by mainstream browsers.
- Internet access for external Leaflet, Leaflet.heat, Chart.js and OpenStreetMap tile resources used by the current templates.

## Setup (Windows PowerShell)

From the repository root:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` in a text editor. Set `SECRET_KEY` to a private random value and set `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DB` to match the local MySQL server. Keep `FLASK_DEBUG=0` unless debugging locally. `.env` is ignored by Git; never paste real credentials into documentation or source control.

Create the schema by following [Database setup](DATABASE_SETUP.md). The SQL migration scripts currently select the database name `netmap_db`; if the configured database name differs, update the `USE netmap_db;` statements in the scripts before applying them, or use the default database name.

## Run

```powershell
.venv\Scripts\Activate.ps1
python app.py
```

Browse to `http://127.0.0.1:5000`. Stop the local server with `Ctrl+C`.

To train the optional Phase 7 model after gathering enough valid and diverse data:

```powershell
python train_model.py
```

The script writes `artifacts/phase7_eda_report.json` and, only when its data/validation gates pass, `artifacts/phase7_connectivity.joblib`. These are generated artifacts and are excluded from Git. If training is skipped, the prediction page explains that the model is not ready.

## Administrator access

Registration creates a normal `user`. There is no public administrator registration. Promote only a trusted account using the controlled SQL procedure in [Database setup](DATABASE_SETUP.md#administrator-account). Then sign out and sign back in at `/admin/login` so the session is refreshed. Do not weaken the role check to fix a 403.

## Troubleshooting

- **MySQL connection error:** confirm the MySQL service is running, `.env` values are correct, and the selected database exists.
- **Missing-table/column error:** new databases should use `schema.sql`; existing databases need the ordered phase migrations. Do not assume `CREATE TABLE IF NOT EXISTS` upgrades old tables.
- **Admin returns 403:** the signed-in database account must have `role='admin'`; see the administrator SQL procedure.
- **Location unavailable:** grant permission in the browser, use a secure context, select a point manually, or continue without coordinates.
- **Map/chart blank:** check browser developer tools and network access to the CDN and OpenStreetMap tiles. The core measurement pages can still operate without GPS; external visual libraries require their scripts/styles to load.
- **Prediction says model unavailable:** collect more labeled location measurements and run `python train_model.py`. The pipeline intentionally refuses to fabricate a model when the dataset is inadequate.
