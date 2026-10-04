USE netmap_db;

-- Jitter may be unmeasurable when too few probes succeed.
ALTER TABLE connectivity_measurements
    MODIFY COLUMN jitter_ms DECIMAL(12, 4) NULL;

-- Safe to rerun: each new scoring field is only added when missing.
SET @phase5_sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'connectivity_measurements'
       AND column_name = 'signal_strength_dbm') = 0,
    'ALTER TABLE connectivity_measurements ADD COLUMN signal_strength_dbm DECIMAL(7, 2) NULL AFTER location_accuracy_m',
    'SELECT ''signal_strength_dbm already exists'''
);
PREPARE phase5_stmt FROM @phase5_sql;
EXECUTE phase5_stmt;
DEALLOCATE PREPARE phase5_stmt;

SET @phase5_sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'connectivity_measurements'
       AND column_name = 'connectivity_score') = 0,
    'ALTER TABLE connectivity_measurements ADD COLUMN connectivity_score DECIMAL(5, 2) NULL AFTER signal_strength_dbm',
    'SELECT ''connectivity_score already exists'''
);
PREPARE phase5_stmt FROM @phase5_sql;
EXECUTE phase5_stmt;
DEALLOCATE PREPARE phase5_stmt;

SET @phase5_sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'connectivity_measurements'
       AND column_name = 'connectivity_classification') = 0,
    'ALTER TABLE connectivity_measurements ADD COLUMN connectivity_classification VARCHAR(20) NULL AFTER connectivity_score',
    'SELECT ''connectivity_classification already exists'''
);
PREPARE phase5_stmt FROM @phase5_sql;
EXECUTE phase5_stmt;
DEALLOCATE PREPARE phase5_stmt;

SET @phase5_sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'connectivity_measurements'
       AND column_name = 'scoring_version') = 0,
    'ALTER TABLE connectivity_measurements ADD COLUMN scoring_version SMALLINT UNSIGNED NULL AFTER connectivity_classification',
    'SELECT ''scoring_version already exists'''
);
PREPARE phase5_stmt FROM @phase5_sql;
EXECUTE phase5_stmt;
DEALLOCATE PREPARE phase5_stmt;

SET @phase5_sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'connectivity_measurements'
       AND column_name = 'scoring_inputs') = 0,
    'ALTER TABLE connectivity_measurements ADD COLUMN scoring_inputs TEXT NULL AFTER scoring_version',
    'SELECT ''scoring_inputs already exists'''
);
PREPARE phase5_stmt FROM @phase5_sql;
EXECUTE phase5_stmt;
DEALLOCATE PREPARE phase5_stmt;
