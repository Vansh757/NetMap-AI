"""Anonymized, filtered aggregate queries for the administrator dashboard."""

from datetime import date, timedelta

VALID_CLASSIFICATIONS = {"Excellent", "Good", "Weak", "Dead Zone"}
DATE_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")
MIN_CELL_SAMPLES = 3


class FilterError(ValueError):
    pass


def parse_filters(args):
    start_text = (args.get("start_date") or "").strip()
    end_text = (args.get("end_date") or "").strip()
    classification = (args.get("classification") or "").strip()
    search = (args.get("search") or "").strip()
    if len(search) > 80:
        raise FilterError("Search must be at most 80 characters.")
    start = end = None
    if start_text or end_text:
        start_text = start_text or end_text
        end_text = end_text or start_text
        if not DATE_RE.fullmatch(start_text) or not DATE_RE.fullmatch(end_text):
            raise FilterError("Dates must use YYYY-MM-DD format.")
        try:
            start, end = date.fromisoformat(start_text), date.fromisoformat(end_text)
        except ValueError as exc:
            raise FilterError("Enter valid calendar dates.") from exc
        if start > end:
            raise FilterError("Start date cannot be after end date.")
        if (end - start).days > 3660:
            raise FilterError("Date range cannot exceed ten years.")
    if classification and classification not in VALID_CLASSIFICATIONS:
        raise FilterError("Choose a valid connectivity classification.")
    return {
        "start": start,
        "end": end,
        "classification": classification,
        "search": search,
    }


def measurement_where(filters, include_location_search=False):
    clauses = ["1 = 1"]
    params = []
    if filters["start"]:
        clauses.extend(["created_at >= %s", "created_at < %s"])
        params.extend([
            f"{filters['start'].isoformat()} 00:00:00",
            f"{(filters['end'] + timedelta(days=1)).isoformat()} 00:00:00",
        ])
    if filters["classification"]:
        clauses.append("connectivity_classification = %s")
        params.append(filters["classification"])
    if include_location_search and filters["search"]:
        literal_search = filters["search"].replace("!", "!!").replace("%", "!%").replace("_", "!_")
        clauses.append(
            "(CAST(ROUND(latitude, 3) AS CHAR) LIKE %s ESCAPE '!' "
            "OR CAST(ROUND(longitude, 3) AS CHAR) LIKE %s ESCAPE '!')"
        )
        params.extend([f"%{literal_search}%", f"%{literal_search}%"])
    return " AND ".join(clauses), params


def query_dashboard(cursor, filters, model_report=None):
    where, params = measurement_where(filters)
    cursor.execute("SELECT COUNT(*) AS total_users FROM users")
    total_users = int(cursor.fetchone()["total_users"] or 0)

    cursor.execute(
        "SELECT COUNT(*) AS total_measurements, AVG(download_mbps) AS average_download_mbps, "
        "AVG(upload_mbps) AS average_upload_mbps, AVG(ping_ms) AS average_latency_ms, "
        "AVG(connectivity_score) AS average_score, "
        "SUM(connectivity_classification = 'Good') AS good_measurements, "
        "SUM(connectivity_classification = 'Excellent') AS excellent_measurements, "
        "SUM(connectivity_classification = 'Weak') AS weak_measurements, "
        "SUM(connectivity_classification = 'Dead Zone') AS dead_zone_measurements "
        "FROM connectivity_measurements WHERE " + where,
        tuple(params),
    )
    summary_row = cursor.fetchone()

    cursor.execute(
        "SELECT connectivity_classification AS classification, COUNT(*) AS total "
        "FROM connectivity_measurements WHERE " + where +
        " GROUP BY connectivity_classification ORDER BY total DESC",
        tuple(params),
    )
    class_counts = {row["classification"]: int(row["total"]) for row in cursor.fetchall() if row["classification"]}

    cursor.execute(
        "SELECT DATE(created_at) AS day, COUNT(*) AS total, AVG(download_mbps) AS average_download_mbps, "
        "AVG(upload_mbps) AS average_upload_mbps, AVG(ping_ms) AS average_latency_ms, "
        "AVG(connectivity_score) AS average_score, "
        "SUM(connectivity_classification IN ('Weak', 'Dead Zone')) AS poor_measurements "
        "FROM connectivity_measurements WHERE " + where +
        " GROUP BY DATE(created_at) ORDER BY day DESC LIMIT 365",
        tuple(params),
    )
    trend = list(reversed(cursor.fetchall()))

    location_where, location_params = measurement_where(filters, include_location_search=True)
    cursor.execute(
        "SELECT ROUND(latitude, 3) AS latitude_cell, ROUND(longitude, 3) AS longitude_cell, "
        "COUNT(*) AS total, AVG(download_mbps) AS average_download_mbps, "
        "AVG(upload_mbps) AS average_upload_mbps, AVG(ping_ms) AS average_latency_ms, "
        "AVG(connectivity_score) AS average_score, "
        "SUM(connectivity_classification = 'Weak') AS weak_measurements, "
        "SUM(connectivity_classification = 'Dead Zone') AS dead_zone_measurements "
        "FROM connectivity_measurements WHERE " + location_where +
        " AND connectivity_classification IS NOT NULL AND latitude IS NOT NULL AND longitude IS NOT NULL "
        "GROUP BY latitude_cell, longitude_cell HAVING COUNT(*) >= %s "
        "ORDER BY (SUM(connectivity_classification IN ('Weak', 'Dead Zone')) / COUNT(*)) DESC, total DESC LIMIT 5000",
        tuple(location_params + [MIN_CELL_SAMPLES]),
    )
    locations = []
    for row in cursor.fetchall():
        total = int(row["total"])
        poor = int(row["weak_measurements"] or 0) + int(row["dead_zone_measurements"] or 0)
        dead = int(row["dead_zone_measurements"] or 0)
        locations.append({
            "latitude": float(row["latitude_cell"]),
            "longitude": float(row["longitude_cell"]),
            "total": total,
            "weak_measurements": int(row["weak_measurements"] or 0),
            "dead_zone_measurements": dead,
            "poor_rate": round(poor / total, 4) if total else 0,
            "average_download_mbps": _float(row["average_download_mbps"]),
            "average_upload_mbps": _float(row["average_upload_mbps"]),
            "average_latency_ms": _float(row["average_latency_ms"]),
            "average_score": _float(row["average_score"]),
            "classification": "Dead Zone" if dead / total >= 0.5 else "Weak" if poor / total >= 0.5 else "Good",
        })

    cursor.execute(
        "SELECT predicted_poor, COUNT(*) AS total FROM connectivity_prediction_events "
        "GROUP BY predicted_poor"
    )
    prediction_counts = {bool(row["predicted_poor"]): int(row["total"]) for row in cursor.fetchall()}
    cursor.execute(
        "SELECT COUNT(*) AS total_predictions, MAX(created_at) AS last_prediction "
        "FROM connectivity_prediction_events"
    )
    prediction_summary = cursor.fetchone()
    cursor.execute(
        "SELECT kind, title, recommendation_text, severity, status, COUNT(*) AS total, MAX(last_seen) AS last_seen "
        "FROM connectivity_recommendations GROUP BY kind, title, recommendation_text, severity, status "
        "ORDER BY FIELD(severity, 'Critical', 'Attention', 'Information'), total DESC LIMIT 50"
    )
    recommendation_groups = cursor.fetchall()

    summary = {
        "total_users": total_users,
        "total_measurements": int(summary_row["total_measurements"] or 0),
        "average_download_mbps": _float(summary_row["average_download_mbps"]),
        "average_upload_mbps": _float(summary_row["average_upload_mbps"]),
        "average_latency_ms": _float(summary_row["average_latency_ms"]),
        "average_score": _float(summary_row["average_score"]),
        "good_measurements": int(summary_row["good_measurements"] or 0) + int(summary_row["excellent_measurements"] or 0),
        "weak_measurements": int(summary_row["weak_measurements"] or 0),
        "dead_zone_measurements": int(summary_row["dead_zone_measurements"] or 0),
        "anonymized_location_cells": len(locations),
        "weak_location_cells": sum(item["classification"] == "Weak" for item in locations),
        "dead_zone_location_cells": sum(item["classification"] == "Dead Zone" for item in locations),
        "good_location_cells": sum(item["classification"] == "Good" for item in locations),
    }
    prediction_metrics = {
        "total_predictions": int(prediction_summary["total_predictions"] or 0),
        "poor_predictions": prediction_counts.get(True, 0),
        "other_predictions": prediction_counts.get(False, 0),
        "last_prediction": prediction_summary["last_prediction"].isoformat(sep=" ", timespec="seconds") if prediction_summary["last_prediction"] else None,
        "model_ready": bool(model_report and model_report.get("training_status") == "trained"),
        "model_name": (model_report or {}).get("selected_model"),
        "test_metrics": (model_report or {}).get("test_metrics", {}),
        "training_status": (model_report or {}).get("training_status", "not_trained"),
    }
    return {
        "summary": summary,
        "classifications": class_counts,
        "trend": [{
            "day": row["day"].isoformat(), "total": int(row["total"]),
            "average_download_mbps": _float(row["average_download_mbps"]),
            "average_upload_mbps": _float(row["average_upload_mbps"]),
            "average_latency_ms": _float(row["average_latency_ms"]),
            "average_score": _float(row["average_score"]),
            "poor_measurements": int(row["poor_measurements"] or 0),
        } for row in trend],
        "locations": locations,
        "recommendations": [{
            "kind": row["kind"], "title": row["title"], "recommendation": row["recommendation_text"],
            "severity": row["severity"], "status": row["status"],
            "total": int(row["total"]), "last_seen": row["last_seen"].isoformat(sep=" ", timespec="seconds") if row["last_seen"] else None,
        } for row in recommendation_groups],
        "prediction_statistics": prediction_metrics,
        "privacy": {"location_cell_precision": 3, "minimum_measurements_per_cell": MIN_CELL_SAMPLES, "user_identifiers_included": False},
        "filters": {
            "start_date": filters["start"].isoformat() if filters["start"] else None,
            "end_date": filters["end"].isoformat() if filters["end"] else None,
            "classification": filters["classification"] or None,
            "search": filters["search"] or None,
        },
    }


def export_analytics(cursor, filters, export_type):
    if export_type == "locations":
        where, params = measurement_where(filters, include_location_search=True)
        cursor.execute(
            "SELECT ROUND(latitude, 3) AS latitude_cell, ROUND(longitude, 3) AS longitude_cell, "
            "COUNT(*) AS measurements, AVG(download_mbps) AS average_download_mbps, "
            "AVG(upload_mbps) AS average_upload_mbps, AVG(ping_ms) AS average_latency_ms, "
            "AVG(connectivity_score) AS average_score, "
            "SUM(connectivity_classification IN ('Weak', 'Dead Zone')) AS poor_measurements "
            "FROM connectivity_measurements WHERE " + where +
            " AND connectivity_classification IS NOT NULL AND latitude IS NOT NULL AND longitude IS NOT NULL "
            "GROUP BY latitude_cell, longitude_cell HAVING COUNT(*) >= %s "
            "ORDER BY measurements DESC LIMIT 5000",
            tuple(params + [MIN_CELL_SAMPLES]),
        )
        headers = ["latitude_cell_approx", "longitude_cell_approx", "measurements", "avg_download_mbps", "avg_upload_mbps", "avg_latency_ms", "avg_score", "poor_measurements"]
        rows = cursor.fetchall()
        return headers, [[
            row["latitude_cell"], row["longitude_cell"], int(row["measurements"]),
            row["average_download_mbps"], row["average_upload_mbps"], row["average_latency_ms"],
            row["average_score"], int(row["poor_measurements"] or 0),
        ] for row in rows]
    where, params = measurement_where(filters)
    if export_type == "classifications":
        cursor.execute(
            "SELECT connectivity_classification, COUNT(*) AS measurements FROM connectivity_measurements WHERE "
            + where + " GROUP BY connectivity_classification ORDER BY measurements DESC",
            tuple(params),
        )
        rows = cursor.fetchall()
        return ["classification", "measurements"], [[row["connectivity_classification"], int(row["measurements"])] for row in rows]
    if export_type != "daily":
        raise FilterError("Choose daily, classifications, or locations for CSV export.")
    cursor.execute(
        "SELECT DATE(created_at) AS day, COUNT(*) AS measurements, AVG(download_mbps) AS average_download_mbps, "
        "AVG(upload_mbps) AS average_upload_mbps, AVG(ping_ms) AS average_latency_ms, "
        "AVG(connectivity_score) AS average_score, "
        "SUM(connectivity_classification IN ('Weak', 'Dead Zone')) AS poor_measurements "
        "FROM connectivity_measurements WHERE " + where +
        " GROUP BY DATE(created_at) ORDER BY day DESC LIMIT 365",
        tuple(params),
    )
    rows = cursor.fetchall()
    headers = ["date", "measurements", "avg_download_mbps", "avg_upload_mbps", "avg_latency_ms", "avg_score", "poor_measurements"]
    return headers, [[
        row["day"].isoformat(), int(row["measurements"]), row["average_download_mbps"],
        row["average_upload_mbps"], row["average_latency_ms"], row["average_score"],
        int(row["poor_measurements"] or 0),
    ] for row in rows]


def _float(value):
    return round(float(value), 2) if value is not None else None
