USE netmap_db;

CREATE TABLE IF NOT EXISTS connectivity_recommendations (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    fingerprint VARCHAR(190) NOT NULL,
    kind VARCHAR(40) NOT NULL,
    title VARCHAR(180) NOT NULL,
    problem TEXT NOT NULL,
    recommendation_text TEXT NOT NULL,
    reason_text TEXT NOT NULL,
    severity ENUM('Information', 'Attention', 'Critical') NOT NULL,
    supporting_measurement_ids TEXT NOT NULL,
    latitude DECIMAL(10, 7) NULL,
    longitude DECIMAL(10, 7) NULL,
    status ENUM('active', 'resolved') NOT NULL DEFAULT 'active',
    first_seen DATETIME NOT NULL,
    last_seen DATETIME NOT NULL,
    resolved_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_recommendations_user_fingerprint (user_id, fingerprint),
    KEY idx_recommendations_user_status_seen (user_id, status, last_seen)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
