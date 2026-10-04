"""Single source of truth for connectivity scoring thresholds and weights."""

SCORING_VERSION = 1

# Scores from each metric are interpolated from its (raw value, score 0-100) curve.
# Weights are normalized across metrics that are actually available for a record.
SCORING_WEIGHTS = {
    "download_mbps": 0.27,
    "upload_mbps": 0.15,
    "ping_ms": 0.25,
    "jitter_ms": 0.15,
    "packet_loss_percent": 0.10,
    "signal_strength_dbm": 0.08,
}

METRIC_SCORE_CURVES = {
    # Higher throughput is better.
    "download_mbps": [(0, 0), (1, 5), (5, 25), (25, 65), (100, 100)],
    "upload_mbps": [(0, 0), (1, 10), (5, 40), (20, 80), (50, 100)],
    # Lower latency, jitter, and packet loss are better.
    "ping_ms": [(0, 100), (20, 100), (50, 85), (100, 65), (250, 30), (500, 0)],
    "jitter_ms": [(0, 100), (5, 90), (20, 70), (50, 35), (100, 0)],
    "packet_loss_percent": [(0, 100), (1, 80), (3, 50), (10, 0)],
    # More negative dBm values indicate weaker signal.
    "signal_strength_dbm": [(-110, 0), (-100, 20), (-80, 55), (-67, 82), (-50, 100)],
}

# Boundaries are inclusive, ordered from best to worst.
CLASSIFICATION_THRESHOLDS = [
    (85, "Excellent"),
    (65, "Good"),
    (35, "Weak"),
    (0, "Dead Zone"),
]
