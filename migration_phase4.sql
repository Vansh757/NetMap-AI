USE netmap_db;

-- Safe to rerun: each column is only added when it is missing.
SET @phase4_sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'connectivity_measurements'
       AND column_name = 'latitude') = 0,
    'ALTER TABLE connectivity_measurements ADD COLUMN latitude DECIMAL(10, 7) NULL AFTER browser_network',
    'SELECT ''latitude already exists'''
);
PREPARE phase4_stmt FROM @phase4_sql;
EXECUTE phase4_stmt;
DEALLOCATE PREPARE phase4_stmt;

SET @phase4_sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'connectivity_measurements'
       AND column_name = 'longitude') = 0,
    'ALTER TABLE connectivity_measurements ADD COLUMN longitude DECIMAL(10, 7) NULL AFTER latitude',
    'SELECT ''longitude already exists'''
);
PREPARE phase4_stmt FROM @phase4_sql;
EXECUTE phase4_stmt;
DEALLOCATE PREPARE phase4_stmt;

SET @phase4_sql = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'connectivity_measurements'
       AND column_name = 'location_accuracy_m') = 0,
    'ALTER TABLE connectivity_measurements ADD COLUMN location_accuracy_m DECIMAL(12, 2) NULL AFTER longitude',
    'SELECT ''location_accuracy_m already exists'''
);
PREPARE phase4_stmt FROM @phase4_sql;
EXECUTE phase4_stmt;
DEALLOCATE PREPARE phase4_stmt;
