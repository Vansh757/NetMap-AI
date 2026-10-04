USE netmap_db;

SET @phase9_sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE() AND table_name = 'users' AND column_name = 'role') = 0,
    'ALTER TABLE users ADD COLUMN role ENUM(''user'', ''admin'') NOT NULL DEFAULT ''user''',
    'SELECT ''users.role already exists'''
);
PREPARE phase9_stmt FROM @phase9_sql;
EXECUTE phase9_stmt;
DEALLOCATE PREPARE phase9_stmt;

SET @phase9_sql = IF(
    (SELECT COUNT(*) FROM information_schema.statistics
     WHERE table_schema = DATABASE() AND table_name = 'connectivity_measurements'
       AND index_name = 'idx_measurements_created') = 0,
    'CREATE INDEX idx_measurements_created ON connectivity_measurements (created_at)',
    'SELECT ''idx_measurements_created already exists'''
);
PREPARE phase9_stmt FROM @phase9_sql;
EXECUTE phase9_stmt;
DEALLOCATE PREPARE phase9_stmt;

SET @phase9_sql = IF(
    (SELECT COUNT(*) FROM information_schema.statistics
     WHERE table_schema = DATABASE() AND table_name = 'connectivity_measurements'
       AND index_name = 'idx_measurements_class_created') = 0,
    'CREATE INDEX idx_measurements_class_created ON connectivity_measurements (connectivity_classification, created_at)',
    'SELECT ''idx_measurements_class_created already exists'''
);
PREPARE phase9_stmt FROM @phase9_sql;
EXECUTE phase9_stmt;
DEALLOCATE PREPARE phase9_stmt;

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
