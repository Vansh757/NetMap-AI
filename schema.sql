CREATE DATABASE IF NOT EXISTS netmap_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE netmap_db;

CREATE TABLE IF NOT EXISTS users (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    username VARCHAR(30) NOT NULL,
    email VARCHAR(254) NOT NULL,
    password VARCHAR(255) NOT NULL,
    role ENUM('user', 'admin') NOT NULL DEFAULT 'user',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_username (username),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS connectivity_measurements (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id INT UNSIGNED NOT NULL,
    download_mbps DECIMAL(12, 4) NOT NULL,
    upload_mbps DECIMAL(12, 4) NOT NULL,
    ping_ms DECIMAL(12, 4) NOT NULL,
    jitter_ms DECIMAL(12, 4) NULL,
    packet_loss_percent DECIMAL(7, 4) NULL,
    browser_network TEXT NOT NULL,
    latitude DECIMAL(10, 7) NULL,
    longitude DECIMAL(10, 7) NULL,
    location_accuracy_m DECIMAL(12, 2) NULL,
    signal_strength_dbm DECIMAL(7, 2) NULL,
    connectivity_score DECIMAL(5, 2) NULL,
    connectivity_classification VARCHAR(20) NULL,
    scoring_version SMALLINT UNSIGNED NULL,
    scoring_inputs TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_measurements_user_created (user_id, created_at),
    KEY idx_measurements_created (created_at),
    KEY idx_measurements_class_created (connectivity_classification, created_at),
    KEY idx_measurements_user_class_created (user_id, connectivity_classification, created_at),
    KEY idx_measurements_user_location (user_id, latitude, longitude),
    CONSTRAINT fk_measurements_user
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS connectivity_recommendations (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id INT UNSIGNED NOT NULL,
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
    KEY idx_recommendations_user_status_seen (user_id, status, last_seen),
    CONSTRAINT fk_recommendations_user
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS connectivity_prediction_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    predicted_poor BOOLEAN NOT NULL,
    latitude_cell DECIMAL(6, 3) NOT NULL,
    longitude_cell DECIMAL(6, 3) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_prediction_events_created (created_at)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contact_messages (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id INT UNSIGNED NULL,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(254) NOT NULL,
    subject VARCHAR(150) NOT NULL,
    message TEXT NOT NULL,
    status ENUM('unread', 'read') NOT NULL DEFAULT 'unread',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_contact_status_created (status, created_at),
    KEY idx_contact_created (created_at),
    CONSTRAINT fk_contact_user
        FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE SET NULL
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
