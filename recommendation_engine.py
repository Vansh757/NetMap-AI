"""Explainable, measurement-backed connectivity recommendations."""

from collections import defaultdict
from math import asin, cos, radians, sin, sqrt

WINDOW_DAYS = 60
MAX_MEASUREMENTS = 1000
POOR_CLASSES = {"Weak", "Dead Zone"}


def _cell(row):
    return (round(float(row["latitude"]), 3), round(float(row["longitude"]), 3))


def _distance_m(left, right):
    lat1, lon1 = radians(float(left["latitude"])), radians(float(left["longitude"]))
    lat2, lon2 = radians(float(right["latitude"])), radians(float(right["longitude"]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    haversine = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(min(1, sqrt(haversine)))


def _candidate(kind, fingerprint, title, problem, recommendation, reason, severity, rows, latitude=None, longitude=None):
    rows = sorted(rows, key=lambda item: (item["created_at"], item["id"]), reverse=True)
    return {
        "fingerprint": fingerprint,
        "kind": kind,
        "title": title,
        "problem": problem,
        "recommendation": recommendation,
        "reason": reason,
        "severity": severity,
        "supporting_measurement_ids": [int(item["id"]) for item in rows[:20]],
        "latitude": latitude,
        "longitude": longitude,
    }


def analyze_measurements(rows):
    """Return recommendations from a bounded set of one user's recent measurements."""
    candidates = []
    located = [row for row in rows if row["latitude"] is not None and row["longitude"] is not None]
    poor = [row for row in rows if row["connectivity_classification"] in POOR_CLASSES]
    overall_rate = len(poor) / len(rows) if rows else 0

    location_groups = defaultdict(list)
    for row in located:
        location_groups[_cell(row)].append(row)

    # A location warning reports the actual recent numerator and denominator.
    for (lat, lon), group in location_groups.items():
        recent = sorted(group, key=lambda item: (item["created_at"], item["id"]), reverse=True)[:10]
        poor_rows = [row for row in recent if row["connectivity_classification"] in POOR_CLASSES]
        total = len(recent)
        rate = len(poor_rows) / total if total else 0
        if total < 5 or rate < 0.4:
            continue
        if rate >= 0.8 and len(poor_rows) >= 8:
            severity = "Critical"
        elif rate >= 0.6:
            severity = "Attention"
        else:
            severity = "Information"
        candidates.append(_candidate(
            "repeated_poor_location", f"location:{lat:.3f}:{lon:.3f}",
            "Repeated poor connectivity at this location",
            f"{len(poor_rows)} of the last {total} measurements here were classified as Weak or Dead Zone.",
            "Investigate network coverage in this area. If you manage the network, review access-point placement; these measurements do not identify the physical cause.",
            f"{len(poor_rows)}/{total} recent measurements ({rate:.0%}) at {lat:.3f}, {lon:.3f} were classified as poor.",
            severity, recent, lat, lon,
        ))

    # Time windows are based on the timestamp returned by MySQL for this user's data.
    periods = {
        "Night (00:00–05:59)": set(range(0, 6)),
        "Morning (06:00–11:59)": set(range(6, 12)),
        "Afternoon (12:00–17:59)": set(range(12, 18)),
        "Evening (18:00–23:59)": set(range(18, 24)),
    }
    for label, hours in periods.items():
        group = [row for row in rows if row["created_at"].hour in hours]
        poor_rows = [row for row in group if row["connectivity_classification"] in POOR_CLASSES]
        rate = len(poor_rows) / len(group) if group else 0
        if len(group) < 5 or rate < 0.4 or rate < overall_rate + 0.15:
            continue
        severity = "Critical" if rate >= 0.8 and len(group) >= 10 else "Attention" if rate >= 0.6 else "Information"
        candidates.append(_candidate(
            "time_period", f"time:{label.split(' ')[0].lower()}",
            f"Connectivity is weaker during {label.split(' ')[0].lower()}",
            f"{len(poor_rows)} of {len(group)} measurements in {label} were classified as poor.",
            "Compare results across this time period and check whether the pattern continues.",
            f"The poor-connectivity rate was {rate:.0%} in {label}, compared with {overall_rate:.0%} across all recent measurements.",
            severity, group,
        ))

    # Connected components of poor readings within 500 m identify a wider cluster.
    # Only clusters spanning at least two rounded location cells are emitted, avoiding
    # duplication of the single-location rule above.
    poor_cells = defaultdict(list)
    for row in located:
        if row["connectivity_classification"] in POOR_CLASSES:
            poor_cells[_cell(row)].append(row)
    cell_points = [
        {"latitude": sum(float(row["latitude"]) for row in group) / len(group),
         "longitude": sum(float(row["longitude"]) for row in group) / len(group),
         "cell": cell}
        for cell, group in poor_cells.items()
    ]
    parent = list(range(len(cell_points)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for index, point in enumerate(cell_points):
        for other_index in range(index):
            other = cell_points[other_index]
            latitude_gap = abs(float(point["latitude"]) - float(other["latitude"]))
            longitude_gap = abs(float(point["longitude"]) - float(other["longitude"]))
            longitude_limit = 0.005 / max(0.01, abs(cos(radians(float(point["latitude"])))) )
            if latitude_gap > 0.005 or longitude_gap > longitude_limit:
                continue
            if _distance_m(point, cell_points[other_index]) <= 500:
                root_a, root_b = find(index), find(other_index)
                if root_a != root_b:
                    parent[root_b] = root_a
    clusters = defaultdict(list)
    for index, point in enumerate(cell_points):
        clusters[find(index)].append(point["cell"])
    for cluster_cells in clusters.values():
        if len(cluster_cells) < 2:
            continue
        cluster = [row for cell in cluster_cells for row in poor_cells[cell]]
        cells = set(cluster_cells)
        if len(cluster) < 3:
            continue
        lat = round(sum(float(row["latitude"]) for row in cluster) / len(cluster), 3)
        lon = round(sum(float(row["longitude"]) for row in cluster) / len(cluster), 3)
        candidates.append(_candidate(
            "nearby_cluster", f"nearby:{lat:.3f}:{lon:.3f}",
            "Nearby measurements show a connectivity problem",
            f"{len(cluster)} poor measurements span {len(cells)} nearby location cells within approximately 500 m.",
            "Review coverage across this area. The measurements show where service was poor, but do not establish why.",
            f"{len(cluster)} Weak or Dead Zone measurements were recorded across {len(cells)} nearby cells.",
            "Critical" if len(cluster) >= 8 else "Attention", cluster, lat, lon,
        ))

    # Detect a recent, meaningful score drop from at least eight earlier samples at
    # the same user's approximate location. Median/MAD resists outlier influence.
    for (lat, lon), group in location_groups.items():
        ordered = sorted(group, key=lambda item: (item["created_at"], item["id"]))
        scored = [row for row in ordered if row["connectivity_score"] is not None]
        if len(scored) < 9:
            continue
        current = scored[-1]
        baseline = scored[-21:-1]
        values = [float(row["connectivity_score"]) for row in baseline]
        median = sorted(values)[len(values) // 2] if len(values) % 2 else (sorted(values)[len(values) // 2 - 1] + sorted(values)[len(values) // 2]) / 2
        deviations = sorted(abs(value - median) for value in values)
        mad = deviations[len(deviations) // 2] if len(deviations) % 2 else (deviations[len(deviations) // 2 - 1] + deviations[len(deviations) // 2]) / 2
        score = float(current["connectivity_score"])
        threshold = max(15.0, 3.0 * 1.4826 * mad)
        if median - score < threshold:
            continue
        candidates.append(_candidate(
            "abnormal_measurement", f"anomaly:{current['id']}",
            "Unusually low connectivity measurement",
            f"The latest score ({score:.1f}) is substantially below the recent baseline.",
            "Repeat the test to check whether the drop persists before taking action.",
            f"The latest score of {score:.1f} is {median - score:.1f} points below the prior {len(values)}-measurement median of {median:.1f}.",
            "Critical" if median - score >= 30 and current["connectivity_classification"] == "Dead Zone" else "Attention",
            [current] + baseline[-9:], lat, lon,
        ))

    return candidates


def refresh_recommendations(cursor, user_id):
    """Reconcile current findings into history; unique fingerprints prevent duplicates."""
    cursor.execute(
        "SELECT id, latitude, longitude, download_mbps, upload_mbps, ping_ms, "
        "connectivity_score, connectivity_classification, created_at "
        "FROM connectivity_measurements WHERE user_id = %s "
        "AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY) "
        "ORDER BY created_at DESC, id DESC LIMIT %s",
        (user_id, WINDOW_DAYS, MAX_MEASUREMENTS),
    )
    rows = cursor.fetchall()
    candidates = analyze_measurements(rows)

    cursor.execute(
        "SELECT fingerprint FROM connectivity_recommendations WHERE user_id = %s AND status = 'active'",
        (user_id,),
    )
    active_before_refresh = {row["fingerprint"] for row in cursor.fetchall()}
    cursor.execute(
        "UPDATE connectivity_recommendations SET status = 'resolved', resolved_at = NOW() "
        "WHERE user_id = %s AND status = 'active'",
        (user_id,),
    )
    for item in candidates:
        base_fingerprint = item["fingerprint"]
        prior_active = next((
            fingerprint for fingerprint in active_before_refresh
            if fingerprint == base_fingerprint or fingerprint.startswith(base_fingerprint + ":episode:")
        ), None)
        if prior_active:
            fingerprint = prior_active
        else:
            cursor.execute(
                "SELECT COUNT(*) AS prior_episodes FROM connectivity_recommendations "
                "WHERE user_id = %s AND (fingerprint = %s OR fingerprint LIKE %s)",
                (user_id, base_fingerprint, f"{base_fingerprint}:episode:%"),
            )
            prior_episodes = int(cursor.fetchone()["prior_episodes"] or 0)
            fingerprint = base_fingerprint if prior_episodes == 0 else f"{base_fingerprint}:episode:{prior_episodes + 1}"
        cursor.execute(
            "INSERT INTO connectivity_recommendations "
            "(user_id, fingerprint, kind, title, problem, recommendation_text, reason_text, "
            "severity, supporting_measurement_ids, latitude, longitude, status, first_seen, last_seen) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', NOW(), NOW()) "
            "ON DUPLICATE KEY UPDATE kind = VALUES(kind), title = VALUES(title), "
            "problem = VALUES(problem), recommendation_text = VALUES(recommendation_text), "
            "reason_text = VALUES(reason_text), severity = VALUES(severity), "
            "supporting_measurement_ids = VALUES(supporting_measurement_ids), "
            "latitude = VALUES(latitude), longitude = VALUES(longitude), status = 'active', "
            "last_seen = NOW(), resolved_at = NULL",
            (
                user_id, fingerprint, item["kind"], item["title"], item["problem"],
                item["recommendation"], item["reason"], item["severity"],
                ",".join(str(identifier) for identifier in item["supporting_measurement_ids"]),
                item["latitude"], item["longitude"],
            ),
        )
    return len(candidates)


def serialize_recommendation(row, measurement_url):
    identifiers = [int(value) for value in (row["supporting_measurement_ids"] or "").split(",") if value.strip().isdigit()]
    return {
        "id": int(row["id"]),
        "kind": row["kind"],
        "title": row["title"],
        "problem": row["problem"],
        "recommendation": row["recommendation_text"],
        "reason": row["reason_text"],
        "severity": row["severity"],
        "status": row["status"],
        "supporting_measurements": [
            {"id": identifier, "url": measurement_url(identifier)} for identifier in identifiers
        ],
        "first_seen": row["first_seen"].isoformat(sep=" ", timespec="seconds"),
        "last_seen": row["last_seen"].isoformat(sep=" ", timespec="seconds"),
        "resolved_at": row["resolved_at"].isoformat(sep=" ", timespec="seconds") if row["resolved_at"] else None,
    }
