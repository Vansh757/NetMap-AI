import os
import re
import json
import math
import csv
import io
from functools import wraps
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

import MySQLdb
import MySQLdb.cursors
from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, make_response, redirect, render_template, request, session, url_for
from flask_mysqldb import MySQL
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash
from scoring import calculate_connectivity_score
from recommendation_engine import refresh_recommendations, serialize_recommendation
from admin_analytics import FilterError, export_analytics, parse_filters, query_dashboard

load_dotenv()

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Set SESSION_COOKIE_SECURE=1 in production (HTTPS). Leave unset or 0 for local HTTP dev.
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
    # Sessions expire after 8 hours of inactivity (requires session.permanent = True per login).
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MYSQL_HOST=os.environ.get("MYSQL_HOST", "localhost"),
    MYSQL_USER=os.environ.get("MYSQL_USER", "root"),
    MYSQL_PASSWORD=os.environ.get("MYSQL_PASSWORD", ""),
    MYSQL_DB=os.environ.get("MYSQL_DB", "netmap_db"),
    MYSQL_PORT=int(os.environ.get("MYSQL_PORT", "3306")),
    MYSQL_CURSORCLASS="DictCursor",
    MAX_CONTENT_LENGTH=4 * 1024 * 1024,
)

mysql = MySQL(app)
csrf = CSRFProtect(app)
# Increase token validity to match session lifetime so long-open tabs don't fail.
app.config["WTF_CSRF_TIME_LIMIT"] = 8 * 3600  # 8 hours

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

ML_MODEL_PATH = Path(__file__).resolve().parent / "artifacts" / "phase7_connectivity.joblib"
ML_REPORT_PATH = Path(__file__).resolve().parent / "artifacts" / "phase7_eda_report.json"

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to access that page.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view


def api_login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify(error="Authentication required."), 401
        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("admin_login", next=request.path))
        cursor = mysql.connection.cursor()
        try:
            cursor.execute("SELECT role FROM users WHERE id = %s LIMIT 1", (session["user_id"],))
            account = cursor.fetchone()
        finally:
            cursor.close()
        if not account or account["role"] != "admin":
            session.pop("role", None)
            abort(403)
        session["role"] = "admin"
        response = make_response(view(*args, **kwargs))
        response.headers["Cache-Control"] = "no-store"
        return response

    return wrapped_view


def api_admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify(error="Authentication required."), 401
        cursor = mysql.connection.cursor()
        try:
            cursor.execute("SELECT role FROM users WHERE id = %s LIMIT 1", (session["user_id"],))
            account = cursor.fetchone()
        finally:
            cursor.close()
        if not account or account["role"] != "admin":
            session.pop("role", None)
            response = jsonify(error="Administrator access required.")
            response.status_code = 403
            response.headers["Cache-Control"] = "no-store"
            return response
        session["role"] = "admin"
        response = make_response(view(*args, **kwargs))
        response.headers["Cache-Control"] = "no-store"
        return response

    return wrapped_view


def safe_return_url(target, default="dashboard"):
    # Only allow local paths so a crafted next parameter cannot redirect away.
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for(default)


@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    if request.path.startswith("/api/") or request.is_json:
        return jsonify(error=f"CSRF authentication failed: {error.description}"), 400
    flash("Session security token expired or is invalid. Please try again.", "warning")
    return redirect(request.referrer or url_for("home"))


@app.errorhandler(429)
def handle_ratelimit_error(error):
    if request.path.startswith("/api/") or request.is_json:
        return jsonify(error=f"Too many requests: {error.description}"), 429
    flash("Too many attempts. Please wait a minute before trying again.", "danger")
    return redirect(request.referrer or url_for("home"))


@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith("/api/") or request.is_json:
        return jsonify(error="Resource not found."), 404
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_server_error(error):
    try:
        mysql.connection.rollback()
    except Exception:
        pass
    app.logger.exception("Internal server error: %s", error)
    if request.path.startswith("/api/") or request.is_json:
        return jsonify(error="An internal server error occurred."), 500
    return render_template("500.html"), 500


@app.context_processor
def inject_admin_feedback_count():
    if session.get("role") == "admin":
        try:
            cursor = mysql.connection.cursor()
            cursor.execute("SELECT COUNT(*) AS total FROM contact_messages WHERE status = 'unread'")
            row = cursor.fetchone()
            cursor.close()
            return {"unread_feedback_count": int(row["total"] if row else 0)}
        except Exception:
            return {"unread_feedback_count": 0}
    return {"unread_feedback_count": 0}


@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self)"

    # Content Security Policy accommodating CDNs used by the application (Bootstrap, Leaflet, Chart.js, OSM)
    csp_directives = [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com",
        "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://tile.openstreetmap.org https://unpkg.com",
        "font-src 'self' https://cdn.jsdelivr.net",
        "connect-src 'self'",
        "frame-ancestors 'none'",
    ]
    response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

    # In production HTTPS, enforce HSTS
    if app.config.get("SESSION_COOKIE_SECURE") or request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def contact():
    values = {"name": "", "email": "", "subject": "", "message": ""}
    # Pre-fill name and email if user is logged in
    if session.get("user_id"):
        values["name"] = session.get("name", "")
        cursor = mysql.connection.cursor()
        try:
            cursor.execute("SELECT email, name FROM users WHERE id = %s LIMIT 1", (session["user_id"],))
            user = cursor.fetchone()
            if user:
                values["name"] = user.get("name") or values["name"]
                values["email"] = user.get("email") or ""
        finally:
            cursor.close()

    if request.method == "POST":
        values["name"] = request.form.get("name", "").strip()
        values["email"] = request.form.get("email", "").strip().lower()
        values["subject"] = request.form.get("subject", "").strip()
        values["message"] = request.form.get("message", "").strip()

        errors = []
        if not values["name"] or len(values["name"]) > 100:
            errors.append("Please enter your name (up to 100 characters).")
        if not values["email"] or len(values["email"]) > 254 or not EMAIL_RE.match(values["email"]):
            errors.append("Please enter a valid email address.")
        if not values["subject"] or len(values["subject"]) > 150:
            errors.append("Please enter a subject (up to 150 characters).")
        if not values["message"] or len(values["message"]) > 3000:
            errors.append("Please enter a message (up to 3,000 characters).")

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("contact.html", values=values)

        cursor = mysql.connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO contact_messages (user_id, name, email, subject, message, status) "
                "VALUES (%s, %s, %s, %s, %s, 'unread')",
                (
                    session.get("user_id"),
                    values["name"],
                    values["email"],
                    values["subject"],
                    values["message"],
                ),
            )
            mysql.connection.commit()
        except Exception:
            mysql.connection.rollback()
            raise
        finally:
            cursor.close()

        flash("Thank you for your feedback! Your message has been received.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html", values=values)


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("admin_dashboard" if session.get("role") == "admin" else "dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Enter both your username and password.", "danger")
            return render_template("login.html", username=username)

        cursor = mysql.connection.cursor()
        try:
            cursor.execute(
                "SELECT id, name, username, password, role FROM users WHERE username = %s LIMIT 1",
                (username,),
            )
            user = cursor.fetchone()
        finally:
            cursor.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            flash("You are now logged in.", "success")
            default_target = "admin_dashboard" if user["role"] == "admin" else "dashboard"
            return redirect(safe_return_url(request.args.get("next"), default=default_target))

        flash("Invalid username or password.", "danger")
        return render_template("login.html", username=username)

    return render_template("login.html", username="")


@app.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def admin_login():
    if session.get("user_id") and session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password or len(username) > 50 or len(password) > 128:
            flash("Enter a valid administrator username and password.", "danger")
            return render_template("admin_login.html", username=username)
        cursor = mysql.connection.cursor()
        try:
            cursor.execute(
                "SELECT id, name, username, password, role FROM users WHERE username = %s LIMIT 1",
                (username,),
            )
            user = cursor.fetchone()
        finally:
            cursor.close()
        if user and user["role"] == "admin" and check_password_hash(user["password"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["name"] = user["name"]
            session["role"] = "admin"
            flash("Administrator sign-in successful.", "success")
            return redirect(safe_return_url(request.args.get("next"), default="admin_dashboard"))
        flash("Invalid administrator credentials.", "danger")
        return render_template("admin_login.html", username=username)
    return render_template("admin_login.html", username="")


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    values = {field: "" for field in ("name", "username", "email")}
    if request.method == "POST":
        values = {
            "name": request.form.get("name", "").strip(),
            "username": request.form.get("username", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
        }
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        errors = []
        if not values["name"] or len(values["name"]) > 100:
            errors.append("Name is required and must be at most 100 characters.")
        if not USERNAME_RE.fullmatch(values["username"]):
            errors.append("Username must be 3-30 characters using letters, numbers, or underscores.")
        if len(values["email"]) > 254 or not EMAIL_RE.fullmatch(values["email"]):
            errors.append("Enter a valid email address (up to 254 characters).")
        if len(password) < 8 or len(password) > 128:
            errors.append("Password must be between 8 and 128 characters.")
        if password != confirm_password:
            errors.append("Passwords do not match.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("register.html", values=values)

        cursor = mysql.connection.cursor()
        try:
            cursor.execute(
                "SELECT id FROM users WHERE username = %s OR email = %s LIMIT 1",
                (values["username"], values["email"]),
            )
            existing_user = cursor.fetchone()
            if existing_user:
                flash("That username or email address is already registered.", "danger")
                return render_template("register.html", values=values)

            cursor.execute(
                "INSERT INTO users (name, username, email, password) VALUES (%s, %s, %s, %s)",
                (
                    values["name"],
                    values["username"],
                    values["email"],
                    generate_password_hash(password),
                ),
            )
            mysql.connection.commit()
        except MySQLdb.IntegrityError:
            # Unique database constraints also protect against simultaneous registrations.
            mysql.connection.rollback()
            flash("That username or email address is already registered.", "danger")
            return render_template("register.html", values=values)
        except Exception:
            mysql.connection.rollback()
            raise
        finally:
            cursor.close()

        flash("Your account was created. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", values=values)


@app.route("/dashboard")
@login_required
def dashboard():
    cursor = mysql.connection.cursor()
    try:
        refresh_recommendations(cursor, session["user_id"])
        mysql.connection.commit()
        cursor.execute(
            "SELECT id, kind, title, problem, recommendation_text, reason_text, severity, "
            "supporting_measurement_ids, status, first_seen, last_seen, resolved_at "
            "FROM connectivity_recommendations WHERE user_id = %s AND status = 'active' "
            "ORDER BY FIELD(severity, 'Critical', 'Attention', 'Information'), last_seen DESC LIMIT 5",
            (session["user_id"],),
        )
        rows = cursor.fetchall()
    except Exception:
        mysql.connection.rollback()
        raise
    finally:
        cursor.close()
    recommendations = [serialize_recommendation(row, lambda mid: url_for("measurement_history", highlight=mid) + f"#measurement-{mid}") for row in rows]
    return render_template("dashboard.html", name=session.get("name", "User"), recommendations=recommendations)


@app.route("/profile")
@login_required
def profile():
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            "SELECT name, username, email FROM users WHERE id = %s LIMIT 1",
            (session["user_id"],),
        )
        user = cursor.fetchone()
    finally:
        cursor.close()

    if user is None:
        session.clear()
        flash("Your account could not be found. Please log in again.", "warning")
        return redirect(url_for("login"))
    return render_template("profile.html", user=user)


@app.route("/connectivity-test")
@login_required
def connectivity_test():
    return render_template("connectivity_test.html")


@app.route("/measurements")
@login_required
def measurement_history():
    highlight_id = request.args.get("highlight", type=int)
    cursor = mysql.connection.cursor()
    try:
        if highlight_id:
            cursor.execute(
                "SELECT id, download_mbps, upload_mbps, ping_ms, jitter_ms, "
                "packet_loss_percent, browser_network, latitude, longitude, "
                "location_accuracy_m, connectivity_score, connectivity_classification, "
                "scoring_version, created_at FROM connectivity_measurements "
                "WHERE user_id = %s AND id = %s LIMIT 1",
                (session["user_id"], highlight_id),
            )
        else:
            cursor.execute(
                "SELECT id, download_mbps, upload_mbps, ping_ms, jitter_ms, "
                "packet_loss_percent, browser_network, latitude, longitude, "
                "location_accuracy_m, connectivity_score, connectivity_classification, "
                "scoring_version, created_at "
                "FROM connectivity_measurements WHERE user_id = %s "
                "ORDER BY created_at DESC LIMIT 100",
                (session["user_id"],),
            )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    for row in rows:
        row["browser_network"] = json.loads(row["browser_network"] or "{}")
    return render_template("measurement_history.html", measurements=rows, highlight_id=highlight_id)


@app.route("/map")
@login_required
def measurement_map():
    return render_template("measurement_map.html")


@app.route("/analytics")
@login_required
def analytics_dashboard():
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            "SELECT latitude, longitude, COUNT(*) AS sample_count "
            "FROM connectivity_measurements WHERE user_id = %s "
            "AND latitude IS NOT NULL AND longitude IS NOT NULL "
            "GROUP BY latitude, longitude ORDER BY sample_count DESC LIMIT 200",
            (session["user_id"],),
        )
        locations = cursor.fetchall()
    finally:
        cursor.close()
    location_options = [
        {
            "value": f"{Decimal(row['latitude']):.7f},{Decimal(row['longitude']):.7f}",
            "label": f"{float(row['latitude']):.5f}, {float(row['longitude']):.5f} ({row['sample_count']} tests)",
        }
        for row in locations
    ]
    today = date.today()
    return render_template(
        "analytics.html",
        locations=location_options,
        default_start_date=(today - timedelta(days=29)).isoformat(),
        default_end_date=today.isoformat(),
    )


@app.route("/predictions")
@login_required
def prediction_dashboard():
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            "SELECT ROUND(latitude, 3) AS latitude_cell, ROUND(longitude, 3) AS longitude_cell, "
            "COUNT(*) AS sample_count FROM connectivity_measurements "
            "WHERE user_id = %s AND latitude IS NOT NULL AND longitude IS NOT NULL "
            "GROUP BY latitude_cell, longitude_cell ORDER BY sample_count DESC LIMIT 200",
            (session["user_id"],),
        )
        locations = cursor.fetchall()
    finally:
        cursor.close()
    model_ready = ML_MODEL_PATH.is_file()
    report = {}
    if ML_REPORT_PATH.is_file():
        try:
            with ML_REPORT_PATH.open(encoding="utf-8") as report_file:
                report = json.load(report_file)
        except (OSError, json.JSONDecodeError):
            report = {}
    return render_template(
        "prediction.html",
        locations=[{
            "value": f"{float(row['latitude_cell']):.3f},{float(row['longitude_cell']):.3f}",
            "label": f"{float(row['latitude_cell']):.3f}, {float(row['longitude_cell']):.3f} ({row['sample_count']} tests)",
        } for row in locations],
        model_ready=model_ready,
        training_report=report,
    )


@app.route("/api/predictions/connectivity", methods=["POST"])
@api_login_required
def predict_connectivity():
    if not ML_MODEL_PATH.is_file():
        reason = "Model not trained yet. Collect more location-enabled measurements, then run train_model.py."
        if ML_REPORT_PATH.is_file():
            try:
                with ML_REPORT_PATH.open(encoding="utf-8") as report_file:
                    reason = json.load(report_file).get("training_reason") or reason
            except (OSError, json.JSONDecodeError):
                pass
        return jsonify(error=reason, model_ready=False), 503

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="A JSON object with latitude and longitude is required."), 400
    coordinate_values = []
    for field, low, high in (("latitude", -90, 90), ("longitude", -180, 180)):
        value = data.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            return jsonify(error=f"{field} must be a finite number between {low} and {high}."), 400
        coordinate_values.append(Decimal(str(value)).quantize(Decimal("0.001")))
    latitude_cell, longitude_cell = coordinate_values
    half_cell = Decimal("0.0005")
    bounds = (
        latitude_cell - half_cell, latitude_cell + half_cell,
        longitude_cell - half_cell, longitude_cell + half_cell,
    )

    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) AS history_count, AVG(download_mbps) AS download_mean, "
            "AVG(upload_mbps) AS upload_mean, AVG(ping_ms) AS latency_mean, "
            "AVG(connectivity_score) AS score_mean "
            "FROM connectivity_measurements WHERE user_id = %s "
            "AND latitude >= %s AND latitude < %s AND longitude >= %s AND longitude < %s "
            "AND created_at <= NOW()",
            (session["user_id"], *bounds),
        )
        history = cursor.fetchone()
        if not history["history_count"]:
            return jsonify(error="You need at least one earlier measurement at this location before it can be predicted."), 422
        cursor.execute(
            "SELECT download_mbps, upload_mbps, ping_ms, connectivity_score "
            "FROM connectivity_measurements WHERE user_id = %s "
            "AND latitude >= %s AND latitude < %s AND longitude >= %s AND longitude < %s "
            "AND created_at <= NOW() ORDER BY created_at DESC, id DESC LIMIT 1",
            (session["user_id"], *bounds),
        )
        previous = cursor.fetchone()
        cursor.execute("SELECT HOUR(NOW()) AS hour, WEEKDAY(NOW()) AS day_of_week")
        now_features = cursor.fetchone()
    finally:
        cursor.close()

    try:
        import joblib
        import pandas as pd
        from ml_pipeline import FEATURES

        artifact = joblib.load(ML_MODEL_PATH)
        row = {
            "latitude": float(latitude_cell),
            "longitude": float(longitude_cell),
            "hour": int(now_features["hour"]),
            "day_of_week": int(now_features["day_of_week"]),
            "previous_download_mbps": float(previous["download_mbps"]) if previous["download_mbps"] is not None else None,
            "previous_upload_mbps": float(previous["upload_mbps"]) if previous["upload_mbps"] is not None else None,
            "previous_latency_ms": float(previous["ping_ms"]) if previous["ping_ms"] is not None else None,
            "previous_connectivity_score": float(previous["connectivity_score"]) if previous["connectivity_score"] is not None else None,
            "history_download_mean_mbps": float(history["download_mean"]) if history["download_mean"] is not None else None,
            "history_upload_mean_mbps": float(history["upload_mean"]) if history["upload_mean"] is not None else None,
            "history_latency_mean_ms": float(history["latency_mean"]) if history["latency_mean"] is not None else None,
            "history_connectivity_score_mean": float(history["score_mean"]) if history["score_mean"] is not None else None,
            "history_measurement_count": int(history["history_count"]),
        }
        prediction = int(artifact["pipeline"].predict(pd.DataFrame([row], columns=FEATURES))[0])
    except Exception:
        app.logger.exception("Could not load or run the connectivity prediction model")
        return jsonify(error="The prediction model could not be loaded. Retrain it with train_model.py."), 503

    event_cursor = mysql.connection.cursor()
    try:
        event_cursor.execute(
            "INSERT INTO connectivity_prediction_events "
            "(predicted_poor, latitude_cell, longitude_cell) VALUES (%s, %s, %s)",
            (prediction, latitude_cell, longitude_cell),
        )
        mysql.connection.commit()
    except Exception:
        mysql.connection.rollback()
        app.logger.exception("Prediction succeeded but its anonymized event could not be recorded")
    finally:
        event_cursor.close()

    return jsonify(
        model_ready=True,
        status="Poor connectivity likely" if prediction == 1 else "Poor connectivity not indicated",
        poor_connectivity_likely=bool(prediction),
        historical_measurements=int(history["history_count"]),
        prediction_scope="your previous measurements at this approximate location",
        confidence=None,
        message="No confidence value is shown because this model has not been probability-calibrated.",
    )


def _load_user_recommendations(cursor, user_id, history=False):
    if history:
        cursor.execute(
            "SELECT id, kind, title, problem, recommendation_text, reason_text, severity, "
            "supporting_measurement_ids, status, first_seen, last_seen, resolved_at "
            "FROM connectivity_recommendations WHERE user_id = %s "
            "ORDER BY last_seen DESC LIMIT 100",
            (user_id,),
        )
    else:
        cursor.execute(
            "SELECT id, kind, title, problem, recommendation_text, reason_text, severity, "
            "supporting_measurement_ids, status, first_seen, last_seen, resolved_at "
            "FROM connectivity_recommendations WHERE user_id = %s AND status = 'active' "
            "ORDER BY FIELD(severity, 'Critical', 'Attention', 'Information'), last_seen DESC LIMIT 50",
            (user_id,),
        )
    return [
        serialize_recommendation(row, lambda mid: url_for("measurement_history", highlight=mid) + f"#measurement-{mid}")
        for row in cursor.fetchall()
    ]


@app.route("/api/recommendations", methods=["GET"])
@api_login_required
def recommendation_data():
    history = request.args.get("history", "").lower() in {"1", "true", "yes"}
    cursor = mysql.connection.cursor()
    try:
        items = _load_user_recommendations(cursor, session["user_id"], history=history)
    finally:
        cursor.close()
    return jsonify(recommendations=items, scope="current_user", history=history)


@app.route("/api/recommendations/refresh", methods=["POST"])
@api_login_required
def refresh_recommendation_data():
    cursor = mysql.connection.cursor()
    try:
        created_or_updated = refresh_recommendations(cursor, session["user_id"])
        mysql.connection.commit()
        items = _load_user_recommendations(cursor, session["user_id"])
    except Exception:
        mysql.connection.rollback()
        raise
    finally:
        cursor.close()
    return jsonify(recommendations=items, refreshed=len(items), evaluated=created_or_updated), 200


@app.route("/recommendations")
@login_required
def recommendation_history():
    cursor = mysql.connection.cursor()
    try:
        refresh_recommendations(cursor, session["user_id"])
        mysql.connection.commit()
        items = _load_user_recommendations(cursor, session["user_id"], history=True)
    except Exception:
        mysql.connection.rollback()
        raise
    finally:
        cursor.close()
    return render_template("recommendations.html", recommendations=items)


def _admin_model_report():
    try:
        if ML_REPORT_PATH.is_file():
            with ML_REPORT_PATH.open(encoding="utf-8") as report_file:
                report = json.load(report_file)
                return report if isinstance(report, dict) else {}
    except (OSError, json.JSONDecodeError):
        app.logger.exception("Could not read the Phase 7 evaluation report")
    return {}


@app.route("/admin")
@admin_required
def admin_dashboard():
    return render_template(
        "admin_dashboard.html",
        dashboard_url=url_for("admin_dashboard_data"),
        export_url=url_for("admin_export_csv"),
        report_url=url_for("admin_project_report"),
    )


@app.route("/admin/api/dashboard")
@api_admin_required
def admin_dashboard_data():
    try:
        filters = parse_filters(request.args)
    except FilterError as error:
        return jsonify(error=str(error)), 400
    cursor = mysql.connection.cursor()
    try:
        result = query_dashboard(cursor, filters, _admin_model_report())
    finally:
        cursor.close()
    return jsonify(result)


@app.route("/admin/export.csv")
@api_admin_required
def admin_export_csv():
    cursor = None
    try:
        filters = parse_filters(request.args)
        export_type = (request.args.get("type") or "daily").strip().lower()
        cursor = mysql.connection.cursor()
        output_headers, rows = export_analytics(cursor, filters, export_type)
    except FilterError as error:
        return jsonify(error=str(error)), 400
    finally:
        if cursor is not None:
            cursor.close()
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(output_headers)
    writer.writerows(rows)
    response = make_response(buffer.getvalue())
    response.mimetype = "text/csv"
    response.headers["Content-Disposition"] = f"attachment; filename=netmap-{export_type}-analytics.csv"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/admin/report.txt")
@api_admin_required
def admin_project_report():
    try:
        filters = parse_filters(request.args)
    except FilterError as error:
        return jsonify(error=str(error)), 400
    cursor = mysql.connection.cursor()
    try:
        data = query_dashboard(cursor, filters, _admin_model_report())
    finally:
        cursor.close()
    summary = data["summary"]
    prediction = data["prediction_statistics"]
    lines = [
        "NetMap AI - Project Report Summary",
        f"Generated: {datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(timespec='seconds')}",
        f"Date filter: {data['filters']['start_date'] or 'all'} to {data['filters']['end_date'] or 'all'}",
        f"Classification filter: {data['filters']['classification'] or 'all'}",
        "",
        "Platform overview (anonymized aggregates)",
        f"Total registered users: {summary['total_users']}",
        f"Measurements in selected range: {summary['total_measurements']}",
        f"Average download speed: {summary['average_download_mbps'] if summary['average_download_mbps'] is not None else 'Unavailable'} Mbps",
        f"Average upload speed: {summary['average_upload_mbps'] if summary['average_upload_mbps'] is not None else 'Unavailable'} Mbps",
        f"Average latency: {summary['average_latency_ms'] if summary['average_latency_ms'] is not None else 'Unavailable'} ms",
        f"Average connectivity score: {summary['average_score'] if summary['average_score'] is not None else 'Unavailable'} / 100",
        f"Weak measurements: {summary['weak_measurements']}",
        f"Dead-zone measurements: {summary['dead_zone_measurements']}",
        f"Coarsened location cells (minimum 3 samples): {summary['anonymized_location_cells']}",
        f"Weak / dead-zone location cells: {summary['weak_location_cells']} / {summary['dead_zone_location_cells']}",
        f"Good location cells: {summary['good_location_cells']}",
        "",
        "Prediction status",
        f"Model trained: {'yes' if prediction['model_ready'] else 'no'}",
        f"Prediction events recorded: {prediction['total_predictions']}",
    ]
    if prediction["model_ready"]:
        lines.append(f"Selected model: {prediction['model_name']}")
        balanced_accuracy = prediction["test_metrics"].get("balanced_accuracy")
        if balanced_accuracy is not None:
            lines.append(f"Held-out balanced accuracy: {balanced_accuracy:.3f}")
    lines.extend([
        "",
        "Privacy note: This report contains aggregate statistics only. Map locations are rounded and suppressed unless a cell has at least three measurements.",
        "Interpretation note: Connectivity patterns do not by themselves establish a physical cause.",
    ])
    response = make_response("\n".join(lines) + "\n")
    response.mimetype = "text/plain"
    response.headers["Content-Disposition"] = "attachment; filename=netmap-project-report.txt"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/admin/feedback")
@admin_required
def admin_feedback():
    current_status = request.args.get("status", "all").strip().lower()
    if current_status not in ("all", "unread", "read"):
        current_status = "all"

    cursor = mysql.connection.cursor()
    try:
        cursor.execute("SELECT status, COUNT(*) AS total FROM contact_messages GROUP BY status")
        counts = {row["status"]: int(row["total"]) for row in cursor.fetchall()}
        count_unread = counts.get("unread", 0)
        count_read = counts.get("read", 0)
        count_all = count_unread + count_read

        if current_status == "all":
            cursor.execute(
                "SELECT id, user_id, name, email, subject, message, status, created_at "
                "FROM contact_messages ORDER BY created_at DESC LIMIT 200"
            )
        else:
            cursor.execute(
                "SELECT id, user_id, name, email, subject, message, status, created_at "
                "FROM contact_messages WHERE status = %s ORDER BY created_at DESC LIMIT 200",
                (current_status,),
            )
        messages = cursor.fetchall()
    finally:
        cursor.close()

    return render_template(
        "admin_feedback.html",
        messages=messages,
        current_status=current_status,
        count_all=count_all,
        count_unread=count_unread,
        count_read=count_read,
    )


@app.route("/admin/feedback/<int:message_id>/status", methods=["POST"])
@admin_required
def admin_feedback_status(message_id):
    new_status = request.form.get("status", "").strip().lower()
    if new_status not in ("read", "unread"):
        flash("Invalid status specified.", "danger")
        return redirect(request.referrer or url_for("admin_feedback"))

    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            "UPDATE contact_messages SET status = %s WHERE id = %s",
            (new_status, message_id),
        )
        mysql.connection.commit()
        if cursor.rowcount:
            flash(f"Message #{message_id} marked as {new_status}.", "success")
        else:
            flash(f"Message #{message_id} was not found.", "warning")
    except Exception:
        mysql.connection.rollback()
        raise
    finally:
        cursor.close()

    return redirect(request.referrer or url_for("admin_feedback"))


@app.route("/admin/feedback/<int:message_id>/delete", methods=["POST"])
@admin_required
def admin_feedback_delete(message_id):
    cursor = mysql.connection.cursor()
    try:
        cursor.execute("DELETE FROM contact_messages WHERE id = %s", (message_id,))
        mysql.connection.commit()
        if cursor.rowcount:
            flash(f"Message #{message_id} has been deleted.", "success")
        else:
            flash(f"Message #{message_id} was not found.", "warning")
    except Exception:
        mysql.connection.rollback()
        raise
    finally:
        cursor.close()

    return redirect(request.referrer or url_for("admin_feedback"))


@app.route("/api/measurements/map")
@api_login_required
def measurement_map_data():
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    classification = request.args.get("classification", "").strip()
    if start_date:
        if not DATE_RE.fullmatch(start_date):
            return jsonify(error="start_date must use YYYY-MM-DD format."), 400
        try:
            date.fromisoformat(start_date)
        except ValueError:
            return jsonify(error="start_date must use YYYY-MM-DD format."), 400
    if end_date:
        if not DATE_RE.fullmatch(end_date):
            return jsonify(error="end_date must use YYYY-MM-DD format."), 400
        try:
            date.fromisoformat(end_date)
        except ValueError:
            return jsonify(error="end_date must use YYYY-MM-DD format."), 400
    if start_date and end_date and start_date > end_date:
        return jsonify(error="start_date cannot be after end_date."), 400
    valid_classifications = {"Excellent", "Good", "Weak", "Dead Zone"}
    if classification and classification not in valid_classifications:
        return jsonify(error="classification must be Excellent, Good, Weak, or Dead Zone."), 400

    clauses = ["user_id = %s"]
    parameters = [session["user_id"]]
    if start_date:
        clauses.append("created_at >= %s")
        parameters.append(f"{start_date} 00:00:00")
    if end_date:
        clauses.append("created_at < DATE_ADD(%s, INTERVAL 1 DAY)")
        parameters.append(end_date)
    if classification:
        clauses.append("connectivity_classification = %s")
        parameters.append(classification)

    where_sql = " AND ".join(clauses)

    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            "SELECT latitude, longitude, location_accuracy_m, download_mbps, "
            "upload_mbps, ping_ms, connectivity_score, connectivity_classification, "
            "created_at FROM connectivity_measurements WHERE "
            + where_sql
            + " AND latitude IS NOT NULL AND longitude IS NOT NULL "
            "ORDER BY created_at DESC LIMIT 2000",
            tuple(parameters),
        )
        rows = cursor.fetchall()
        cursor.execute(
            "SELECT COUNT(*) AS total_measurements, AVG(download_mbps) AS avg_download_mbps, "
            "AVG(upload_mbps) AS avg_upload_mbps, AVG(ping_ms) AS avg_ping_ms, "
            "SUM(connectivity_classification = 'Weak') AS weak_locations, "
            "SUM(connectivity_classification = 'Dead Zone') AS dead_zone_measurements "
            "FROM connectivity_measurements WHERE " + where_sql,
            tuple(parameters),
        )
        stats_row = cursor.fetchone()
        cursor.execute(
            "SELECT DATE(created_at) AS measurement_day, AVG(download_mbps) AS avg_download_mbps, "
            "AVG(ping_ms) AS avg_ping_ms, COUNT(*) AS total "
            "FROM connectivity_measurements WHERE " + where_sql
            + " GROUP BY DATE(created_at) ORDER BY measurement_day ASC",
            tuple(parameters),
        )
        timeline_rows = cursor.fetchall()
        cursor.execute(
            "SELECT connectivity_classification AS classification, COUNT(*) AS total "
            "FROM connectivity_measurements WHERE " + where_sql
            + " GROUP BY connectivity_classification",
            tuple(parameters),
        )
        class_rows = cursor.fetchall()
    finally:
        cursor.close()

    points = []
    for row in rows:
        # Do not serialize user_id, name, username, email, or other account fields.
        points.append({
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "location_accuracy_m": (
                float(row["location_accuracy_m"])
                if row["location_accuracy_m"] is not None else None
            ),
            "download_mbps": float(row["download_mbps"]),
            "upload_mbps": float(row["upload_mbps"]),
            "ping_ms": float(row["ping_ms"]),
            "created_at": row["created_at"].isoformat(
                sep=" ", timespec="seconds"
            ),
            "score": (
                float(row["connectivity_score"])
                if row["connectivity_score"] is not None
                else None
            ),
            "classification": row["connectivity_classification"],
        })

    def nullable_float(value):
        return round(float(value), 2) if value is not None else None

    stats = {
        "total_measurements": int(stats_row["total_measurements"] or 0),
        "average_download_mbps": nullable_float(stats_row["avg_download_mbps"]),
        "average_upload_mbps": nullable_float(stats_row["avg_upload_mbps"]),
        "average_ping_ms": nullable_float(stats_row["avg_ping_ms"]),
        "weak_locations": int(stats_row["weak_locations"] or 0),
        "dead_zone_measurements": int(stats_row["dead_zone_measurements"] or 0),
    }
    timeline = [
        {
            "day": row["measurement_day"].isoformat(),
            "average_download_mbps": nullable_float(row["avg_download_mbps"]),
            "average_ping_ms": nullable_float(row["avg_ping_ms"]),
            "total": int(row["total"]),
        }
        for row in timeline_rows
    ]
    class_counts = {
        row["classification"]: int(row["total"])
        for row in class_rows
        if row["classification"] is not None
    }
    return jsonify(
        measurements=points,
        stats=stats,
        timeline=timeline,
        classification_counts=class_counts,
        scope="current_user",
    )


@app.route("/api/analytics")
@api_login_required
def analytics_data():
    start_value = request.args.get("start_date", "").strip()
    end_value = request.args.get("end_date", "").strip()
    classification = request.args.get("classification", "").strip()
    location = request.args.get("location", "").strip()
    valid_classifications = {"Excellent", "Good", "Weak", "Dead Zone"}

    start_date = end_date = None
    if start_value or end_value:
        start_value = start_value or end_value
        end_value = end_value or start_value
        if not DATE_RE.fullmatch(start_value) or not DATE_RE.fullmatch(end_value):
            return jsonify(error="Dates must use YYYY-MM-DD format."), 400
        try:
            start_date = date.fromisoformat(start_value)
            end_date = date.fromisoformat(end_value)
        except ValueError:
            return jsonify(error="Dates must use valid YYYY-MM-DD values."), 400
        if start_date > end_date:
            return jsonify(error="Start date cannot be after end date."), 400

    if classification and classification not in valid_classifications:
        return jsonify(error="Invalid connectivity classification."), 400

    base_clauses = ["user_id = %s"]
    base_params = [session["user_id"]]
    if classification:
        base_clauses.append("connectivity_classification = %s")
        base_params.append(classification)
    if location:
        if len(location) > 80 or location.count(",") != 1:
            return jsonify(error="Invalid location filter."), 400
        latitude_text, longitude_text = location.split(",", 1)
        try:
            latitude = Decimal(latitude_text)
            longitude = Decimal(longitude_text)
        except InvalidOperation:
            return jsonify(error="Invalid location filter."), 400
        if (
            not latitude.is_finite()
            or not longitude.is_finite()
            or not Decimal("-90") <= latitude <= Decimal("90")
            or not Decimal("-180") <= longitude <= Decimal("180")
        ):
            return jsonify(error="Location coordinates are out of range."), 400
        base_clauses.extend(["latitude = %s", "longitude = %s"])
        base_params.extend([str(latitude), str(longitude)])

    filtered_clauses = list(base_clauses)
    filtered_params = list(base_params)
    if start_date:
        filtered_clauses.extend(["created_at >= %s", "created_at < %s"])
        filtered_params.extend([
            f"{start_date.isoformat()} 00:00:00",
            f"{(end_date + timedelta(days=1)).isoformat()} 00:00:00",
        ])
    filtered_where = " AND ".join(filtered_clauses)
    base_where = " AND ".join(base_clauses)

    # All queries aggregate in MySQL. No measurement-level history is sent to the browser.
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) AS total_measurements, "
            "AVG(download_mbps) AS average_download_mbps, "
            "AVG(upload_mbps) AS average_upload_mbps, "
            "AVG(ping_ms) AS average_latency_ms, "
            "AVG(connectivity_score) AS average_score, "
            "COUNT(DISTINCT CASE WHEN connectivity_classification IN ('Excellent', 'Good') "
            "THEN CONCAT(latitude, ',', longitude) END) AS good_locations, "
            "COUNT(DISTINCT CASE WHEN connectivity_classification = 'Weak' "
            "THEN CONCAT(latitude, ',', longitude) END) AS weak_locations, "
            "SUM(connectivity_classification = 'Dead Zone') AS dead_zone_measurements "
            "FROM connectivity_measurements WHERE " + filtered_where,
            tuple(filtered_params),
        )
        summary_row = cursor.fetchone()

        cursor.execute(
            "SELECT connectivity_classification AS classification, COUNT(*) AS total "
            "FROM connectivity_measurements WHERE " + filtered_where
            + " GROUP BY connectivity_classification",
            tuple(filtered_params),
        )
        class_rows = cursor.fetchall()

        cursor.execute(
            "SELECT CASE "
            "WHEN HOUR(created_at) BETWEEN 6 AND 11 THEN 'Morning' "
            "WHEN HOUR(created_at) BETWEEN 12 AND 17 THEN 'Afternoon' "
            "WHEN HOUR(created_at) BETWEEN 18 AND 21 THEN 'Evening' "
            "ELSE 'Night' END AS time_period, "
            "AVG(connectivity_score) AS average_score, "
            "AVG(download_mbps) AS average_download_mbps, COUNT(*) AS total "
            "FROM connectivity_measurements WHERE " + filtered_where
            + " GROUP BY time_period "
            "ORDER BY FIELD(time_period, 'Morning', 'Afternoon', 'Evening', 'Night')",
            tuple(filtered_params),
        )
        time_rows = cursor.fetchall()

        cursor.execute(
            "SELECT DAYOFWEEK(created_at) AS weekday_number, "
            "AVG(connectivity_score) AS average_score, COUNT(*) AS total "
            "FROM connectivity_measurements WHERE " + filtered_where
            + " GROUP BY weekday_number ORDER BY weekday_number",
            tuple(filtered_params),
        )
        weekday_rows = cursor.fetchall()

        cursor.execute(
            "SELECT DATE(created_at) AS measurement_day, "
            "AVG(connectivity_score) AS average_score, "
            "AVG(download_mbps) AS average_download_mbps, "
            "AVG(upload_mbps) AS average_upload_mbps, "
            "AVG(ping_ms) AS average_latency_ms, COUNT(*) AS total "
            "FROM connectivity_measurements WHERE " + filtered_where
            + " GROUP BY DATE(created_at) ORDER BY measurement_day DESC LIMIT 730",
            tuple(filtered_params),
        )
        trend_rows = list(reversed(cursor.fetchall()))

        location_where = filtered_where + " AND latitude IS NOT NULL AND longitude IS NOT NULL"
        cursor.execute(
            "SELECT latitude, longitude, AVG(connectivity_score) AS average_score, "
            "AVG(download_mbps) AS average_download_mbps, AVG(upload_mbps) AS average_upload_mbps, "
            "AVG(ping_ms) AS average_latency_ms, COUNT(*) AS total "
            "FROM connectivity_measurements WHERE " + location_where
            + " GROUP BY latitude, longitude ORDER BY average_score DESC LIMIT 10",
            tuple(filtered_params),
        )
        location_rows = cursor.fetchall()

        cursor.execute(
            "SELECT latitude, longitude, AVG(connectivity_score) AS average_score, "
            "AVG(download_mbps) AS average_download_mbps, AVG(upload_mbps) AS average_upload_mbps, "
            "AVG(ping_ms) AS average_latency_ms, COUNT(*) AS total "
            "FROM connectivity_measurements WHERE " + location_where
            + " GROUP BY latitude, longitude "
            "ORDER BY (average_score IS NULL) ASC, average_score ASC LIMIT 1",
            tuple(filtered_params),
        )
        worst_location_row = cursor.fetchone()

        compare_end = end_date or date.today()
        compare_start = start_date or (compare_end - timedelta(days=29))
        period_length = (compare_end - compare_start).days + 1
        previous_end = compare_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_length - 1)

        comparison_sql = (
            "SELECT COUNT(*) AS total_measurements, AVG(download_mbps) AS average_download_mbps, "
            "AVG(upload_mbps) AS average_upload_mbps, AVG(ping_ms) AS average_latency_ms, "
            "AVG(connectivity_score) AS average_score FROM connectivity_measurements WHERE "
            + base_where
            + " AND created_at >= %s AND created_at < %s"
        )
        comparison_results = []
        for period_start, period_end in (
            (compare_start, compare_end + timedelta(days=1)),
            (previous_start, previous_end + timedelta(days=1)),
        ):
            cursor.execute(
                comparison_sql,
                tuple(base_params + [
                    f"{period_start.isoformat()} 00:00:00",
                    f"{period_end.isoformat()} 00:00:00",
                ]),
            )
            comparison_results.append(cursor.fetchone())
    finally:
        cursor.close()

    def as_float(value):
        return round(float(value), 2) if value is not None else None

    def serialize_location(row):
        if not row:
            return None
        return {
            "label": f"{float(row['latitude']):.5f}, {float(row['longitude']):.5f}",
            "average_score": as_float(row["average_score"]),
            "average_download_mbps": as_float(row["average_download_mbps"]),
            "average_upload_mbps": as_float(row["average_upload_mbps"]),
            "average_latency_ms": as_float(row["average_latency_ms"]),
            "total": int(row["total"]),
        }

    def serialize_period(row):
        return {
            "total_measurements": int(row["total_measurements"] or 0),
            "average_download_mbps": as_float(row["average_download_mbps"]),
            "average_upload_mbps": as_float(row["average_upload_mbps"]),
            "average_latency_ms": as_float(row["average_latency_ms"]),
            "average_score": as_float(row["average_score"]),
        }

    weekday_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    best_location = serialize_location(location_rows[0] if location_rows else None)
    worst_location = serialize_location(worst_location_row)
    return jsonify(
        filters={
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "classification": classification or None,
        },
        summary={
            "total_measurements": int(summary_row["total_measurements"] or 0),
            "average_download_mbps": as_float(summary_row["average_download_mbps"]),
            "average_upload_mbps": as_float(summary_row["average_upload_mbps"]),
            "average_latency_ms": as_float(summary_row["average_latency_ms"]),
            "average_score": as_float(summary_row["average_score"]),
            "good_locations": int(summary_row["good_locations"] or 0),
            "weak_locations": int(summary_row["weak_locations"] or 0),
            "dead_zone_measurements": int(summary_row["dead_zone_measurements"] or 0),
        },
        classifications={
            row["classification"]: int(row["total"])
            for row in class_rows if row["classification"] is not None
        },
        by_time_of_day=[{
            "period": row["time_period"],
            "average_score": as_float(row["average_score"]),
            "average_download_mbps": as_float(row["average_download_mbps"]),
            "total": int(row["total"]),
        } for row in time_rows],
        by_weekday=[{
            "day": weekday_names[int(row["weekday_number"]) - 1],
            "average_score": as_float(row["average_score"]),
            "total": int(row["total"]),
        } for row in weekday_rows],
        trend=[{
            "day": row["measurement_day"].isoformat(),
            "average_score": as_float(row["average_score"]),
            "average_download_mbps": as_float(row["average_download_mbps"]),
            "average_upload_mbps": as_float(row["average_upload_mbps"]),
            "average_latency_ms": as_float(row["average_latency_ms"]),
            "total": int(row["total"]),
        } for row in trend_rows],
        locations=[serialize_location(row) for row in location_rows],
        best_location=best_location,
        worst_location=worst_location,
        comparison={
            "current_label": f"{compare_start.isoformat()} to {compare_end.isoformat()}",
            "previous_label": f"{previous_start.isoformat()} to {previous_end.isoformat()}",
            "current": serialize_period(comparison_results[0]),
            "previous": serialize_period(comparison_results[1]),
        },
    )


@app.route("/measurements/<int:measurement_id>/delete", methods=["POST"])
@login_required
def delete_measurement(measurement_id):
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            "DELETE FROM connectivity_measurements WHERE id = %s AND user_id = %s",
            (measurement_id, session["user_id"]),
        )
        mysql.connection.commit()
        deleted = cursor.rowcount
    finally:
        cursor.close()
    if deleted:
        flash("Measurement deleted.", "success")
    else:
        flash("Measurement not found.", "warning")
    return redirect(url_for("measurement_history"))


@app.route("/api/connectivity/ping")
@api_login_required
def connectivity_ping():
    response = make_response("ok", 200)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response


@app.route("/api/connectivity/download")
@api_login_required
def connectivity_download():
    try:
        byte_count = int(request.args.get("bytes", "0"))
    except ValueError:
        return jsonify(error="bytes must be an integer."), 400
    if not 1 <= byte_count <= 4 * 1024 * 1024:
        return jsonify(error="bytes must be between 1 and 4194304."), 400
    response = make_response(bytes(byte_count), 200)
    response.headers["Content-Type"] = "application/octet-stream"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Content-Length"] = str(byte_count)
    return response


@app.route("/api/connectivity/upload", methods=["POST"])
@csrf.exempt
@api_login_required
def connectivity_upload():
    if request.mimetype != "application/octet-stream":
        return jsonify(error="Send the probe as application/octet-stream."), 415
    payload = request.get_data(cache=False)
    if not 1 <= len(payload) <= 4 * 1024 * 1024:
        return jsonify(error="Upload probe must be between 1 byte and 4 MiB."), 400
    response = make_response("ok", 200)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


@app.route("/api/measurements", methods=["POST"])
@api_login_required
def save_measurement():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="A JSON measurement object is required."), 400

    numeric_fields = {
        "download_mbps": (0, 10000),
        "upload_mbps": (0, 10000),
        "ping_ms": (0, 60000),
    }
    values = {}
    for field, (minimum, maximum) in numeric_fields.items():
        value = data.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return jsonify(error=f"{field} must be a number."), 400
        value = float(value)
        if not math.isfinite(value) or not minimum <= value <= maximum:
            return jsonify(error=f"{field} is outside the accepted range."), 400
        values[field] = value
    jitter_value = data.get("jitter_ms")
    if jitter_value is None:
        values["jitter_ms"] = None
    elif isinstance(jitter_value, bool) or not isinstance(jitter_value, (int, float)):
        return jsonify(error="jitter_ms must be a number or null."), 400
    elif not math.isfinite(float(jitter_value)) or not 0 <= float(jitter_value) <= 60000:
        return jsonify(error="jitter_ms is outside the accepted range."), 400
    else:
        values["jitter_ms"] = float(jitter_value)

    latitude = data.get("latitude")
    longitude = data.get("longitude")
    accuracy = data.get("location_accuracy_m")
    if (latitude is None) != (longitude is None):
        return jsonify(error="Latitude and longitude must be provided together."), 400
    if latitude is not None:
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (latitude, longitude)):
            return jsonify(error="Latitude and longitude must be numbers."), 400
        if not math.isfinite(latitude) or not -90 <= latitude <= 90:
            return jsonify(error="Latitude must be between -90 and 90."), 400
        if not math.isfinite(longitude) or not -180 <= longitude <= 180:
            return jsonify(error="Longitude must be between -180 and 180."), 400
        latitude, longitude = float(latitude), float(longitude)
        if accuracy is not None:
            if isinstance(accuracy, bool) or not isinstance(accuracy, (int, float)) or not math.isfinite(accuracy) or not 0 <= accuracy <= 1000000:
                return jsonify(error="Location accuracy must be between 0 and 1,000,000 meters."), 400
            accuracy = float(accuracy)
    elif accuracy is not None:
        return jsonify(error="Location accuracy requires coordinates."), 400

    network = data.get("browser_network", {})
    if not isinstance(network, dict) or len(network) > 12:
        return jsonify(error="browser_network must be a small JSON object."), 400
    allowed_network_keys = {"effectiveType", "type", "downlink", "rtt", "saveData", "online"}
    if not set(network).issubset(allowed_network_keys):
        return jsonify(error="browser_network contains an unsupported field."), 400
    for key, value in network.items():
        if key in {"effectiveType", "type"}:
            if not isinstance(value, str) or len(value) > 30:
                return jsonify(error=f"browser_network.{key} is invalid."), 400
        elif key in {"saveData", "online"}:
            if not isinstance(value, bool):
                return jsonify(error=f"browser_network.{key} must be boolean."), 400
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value > 100000:
            return jsonify(error=f"browser_network.{key} is invalid."), 400

    # Browser JavaScript cannot measure packet loss or Wi-Fi signal strength here.
    network_json = json.dumps(network, separators=(",", ":"))
    score_result = calculate_connectivity_score({
        "download_mbps": values["download_mbps"],
        "upload_mbps": values["upload_mbps"],
        "ping_ms": values["ping_ms"],
        "jitter_ms": values["jitter_ms"],
        "packet_loss_percent": None,
        "signal_strength_dbm": None,
    })
    scoring_inputs_json = json.dumps(score_result, separators=(",", ":"))
    cursor = mysql.connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO connectivity_measurements "
            "(user_id, download_mbps, upload_mbps, ping_ms, jitter_ms, "
            "packet_loss_percent, browser_network, latitude, longitude, location_accuracy_m, "
            "signal_strength_dbm, connectivity_score, connectivity_classification, "
            "scoring_version, scoring_inputs) "
            "VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, NULL, %s, %s, %s, %s)",
            (
                session["user_id"],
                values["download_mbps"],
                values["upload_mbps"],
                values["ping_ms"],
                values["jitter_ms"],
                network_json,
                latitude,
                longitude,
                accuracy,
                score_result["score"],
                score_result["classification"],
                score_result["version"],
                scoring_inputs_json,
            ),
        )
        mysql.connection.commit()
        measurement_id = cursor.lastrowid
        cursor.execute(
            "SELECT created_at FROM connectivity_measurements WHERE id = %s AND user_id = %s",
            (measurement_id, session["user_id"]),
        )
        saved = cursor.fetchone()
    except Exception:
        mysql.connection.rollback()
        raise
    finally:
        cursor.close()

    return jsonify(
        id=measurement_id,
        created_at=saved["created_at"].isoformat(sep=" ", timespec="seconds"),
        packet_loss_percent=None,
        latitude=latitude,
        longitude=longitude,
        location_accuracy_m=accuracy,
        connectivity_score=score_result["score"],
        connectivity_classification=score_result["classification"],
        jitter_ms=values["jitter_ms"],
    ), 201


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


if __name__ == "__main__":
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("Set SECRET_KEY in your .env file before starting the app.")
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
