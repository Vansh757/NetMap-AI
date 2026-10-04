# Phase 5 connectivity scoring

## Database upgrade

For an existing Phase 4 database, run `migration_phase5.sql` once against
`netmap_db`, then run `python backfill_scores.py` from the project folder. The
backfill scores existing rows from the measurements they already contain;
unavailable packet loss and signal strength remain null. Fresh databases created
from the updated `schema.sql` do not need the backfill unless they already contain
measurements.

## What the score means

Each measurement receives a score from 0 to 100 and one class:

| Score | Classification |
| ---: | --- |
| 85–100 | Excellent |
| 65–84.99 | Good |
| 35–64.99 | Weak |
| 0–34.99 | Dead Zone |

This is an application-defined summary of one test. It is not an ISP certification,
radio survey, or prediction of coverage between measured points. In particular,
the `Dead Zone` label means that the configured score fell below its cutoff; it is
not proof that a place has no radio signal or zero connectivity.

## Formula

Each available raw metric is first converted to a 0–100 subscore by linearly
interpolating the breakpoints in `scoring_config.py`. The final score is a weighted
mean of only the metrics actually present:

```text
connectivity_score =
    sum(metric_subscore * configured_weight for available metrics)
    / sum(configured_weight for available metrics)
```

The included configured weights are:

| Metric | Weight | Current browser test |
| --- | ---: | --- |
| Download throughput | 0.27 | Measured as browser-to-NetMap-server transfer estimate |
| Upload throughput | 0.15 | Measured as browser-to-NetMap-server transfer estimate |
| HTTP latency | 0.25 | Average browser request/response time to this server |
| Jitter | 0.15 | Mean absolute change between successful HTTP latency probes; omitted if fewer than two probes succeed |
| Packet loss | 0.10 | Unavailable; omitted. Browser HTTP failures are not treated as packet loss |
| Wi-Fi signal strength | 0.08 | Unavailable to this browser; omitted |

For the current browser measurements, the available weights (download, upload,
latency, and measurable jitter) are renormalized by their available-weight sum.
If jitter is unavailable, its weight is excluded too. Missing metrics are never
filled with zero or another invented value.

## Raw-value breakpoints

The score curves in `scoring_config.py` are the editable scoring policy. Current
breakpoints are shown below as `raw value -> subscore`:

- Download Mbps: `0 -> 0`, `1 -> 5`, `5 -> 25`, `25 -> 65`, `100 -> 100`.
- Upload Mbps: `0 -> 0`, `1 -> 10`, `5 -> 40`, `20 -> 80`, `50 -> 100`.
- HTTP latency ms: `0 -> 100`, `20 -> 100`, `50 -> 85`, `100 -> 65`, `250 -> 30`, `500 -> 0`.
- Jitter ms: `0 -> 100`, `5 -> 90`, `20 -> 70`, `50 -> 35`, `100 -> 0`.
- Packet loss percent (if a future trusted measurement source supplies it): `0 -> 100`, `1 -> 80`, `3 -> 50`, `10 -> 0`.
- Signal strength dBm (if a future supported source supplies it): `-110 -> 0`, `-100 -> 20`, `-80 -> 55`, `-67 -> 82`, `-50 -> 100`.

Values outside a curve are clamped to its nearest endpoint. `SCORING_VERSION` and
the actual metric inputs, per-metric subscores, and normalized weights are saved
with every measurement so a stored result can be interpreted using the policy
that produced it.

## Heatmap interpretation

The Leaflet heat layer includes only geolocated Weak and Dead Zone measurements.
Intensity is `max(0.12, (100 - score) / 100)`. Hotter areas mean more and/or more
severe poor measurements are close together at the current map zoom. The heatmap
does not estimate unmeasured areas. Both markers and the heatmap are limited to
the signed-in user's own measurements.
