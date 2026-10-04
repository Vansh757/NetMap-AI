"""Backfill Phase 5 scores on measurements created before the scoring columns existed."""

import json

from app import app, mysql
from scoring import calculate_connectivity_score


def backfill_scores():
    with app.app_context():
        cursor = mysql.connection.cursor()
        try:
            cursor.execute(
                "SELECT id, download_mbps, upload_mbps, ping_ms, jitter_ms, "
                "packet_loss_percent, signal_strength_dbm "
                "FROM connectivity_measurements WHERE connectivity_score IS NULL"
            )
            rows = cursor.fetchall()
            for row in rows:
                result = calculate_connectivity_score({
                    "download_mbps": row["download_mbps"],
                    "upload_mbps": row["upload_mbps"],
                    "ping_ms": row["ping_ms"],
                    "jitter_ms": row["jitter_ms"],
                    "packet_loss_percent": row["packet_loss_percent"],
                    "signal_strength_dbm": row["signal_strength_dbm"],
                })
                cursor.execute(
                    "UPDATE connectivity_measurements SET connectivity_score = %s, "
                    "connectivity_classification = %s, scoring_version = %s, scoring_inputs = %s "
                    "WHERE id = %s AND connectivity_score IS NULL",
                    (
                        result["score"],
                        result["classification"],
                        result["version"],
                        json.dumps(result, separators=(",", ":")),
                        row["id"],
                    ),
                )
            mysql.connection.commit()
            print(f"Scored {len(rows)} existing measurement(s).")
        except Exception:
            mysql.connection.rollback()
            raise
        finally:
            cursor.close()


if __name__ == "__main__":
    backfill_scores()
