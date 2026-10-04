import math

from scoring_config import (
    CLASSIFICATION_THRESHOLDS,
    METRIC_SCORE_CURVES,
    SCORING_VERSION,
    SCORING_WEIGHTS,
)


def _interpolate(metric_name, value):
    curve = METRIC_SCORE_CURVES[metric_name]
    value = float(value)
    if value <= curve[0][0]:
        return float(curve[0][1])
    if value >= curve[-1][0]:
        return float(curve[-1][1])

    for (left_x, left_y), (right_x, right_y) in zip(curve, curve[1:]):
        if left_x <= value <= right_x:
            fraction = (value - left_x) / (right_x - left_x)
            return float(left_y + fraction * (right_y - left_y))
    return float(curve[-1][1])


def classify_score(score):
    for threshold, label in CLASSIFICATION_THRESHOLDS:
        if score >= threshold:
            return label
    return "Dead Zone"


def calculate_connectivity_score(metrics):
    """Score available metrics only; missing browser metrics are never imputed."""
    available = {}
    metric_scores = {}
    available_weights = {}

    for name, weight in SCORING_WEIGHTS.items():
        value = metrics.get(name)
        if value is None or weight <= 0:
            continue
        if isinstance(value, bool):
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric_value):
            continue
        available[name] = numeric_value
        metric_scores[name] = _interpolate(name, numeric_value)
        available_weights[name] = float(weight)

    weight_total = sum(available_weights.values())
    if not metric_scores or weight_total <= 0:
        return {
            "score": None,
            "classification": None,
            "version": SCORING_VERSION,
            "inputs": {},
            "metric_scores": {},
            "normalized_weights": {},
        }

    normalized_weights = {
        name: weight / weight_total for name, weight in available_weights.items()
    }
    raw_score = sum(metric_scores[name] * normalized_weights[name] for name in metric_scores)
    score = round(max(0.0, min(100.0, raw_score)), 2)
    return {
        "score": score,
        "classification": classify_score(score),
        "version": SCORING_VERSION,
        "inputs": available,
        "metric_scores": {name: round(value, 2) for name, value in metric_scores.items()},
        "normalized_weights": {
            name: round(value, 6) for name, value in normalized_weights.items()
        },
    }
