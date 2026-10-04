USE netmap_db;

SET @phase6_sql = IF(
    (SELECT COUNT(*) FROM information_schema.statistics
     WHERE table_schema = DATABASE()
       AND table_name = 'connectivity_measurements'
       AND index_name = 'idx_measurements_user_class_created') = 0,
    'CREATE INDEX idx_measurements_user_class_created ON connectivity_measurements (user_id, connectivity_classification, created_at)',
    'SELECT ''idx_measurements_user_class_created already exists'''
);
PREPARE phase6_stmt FROM @phase6_sql;
EXECUTE phase6_stmt;
DEALLOCATE PREPARE phase6_stmt;

SET @phase6_sql = IF(
    (SELECT COUNT(*) FROM information_schema.statistics
     WHERE table_schema = DATABASE()
       AND table_name = 'connectivity_measurements'
       AND index_name = 'idx_measurements_user_location') = 0,
    'CREATE INDEX idx_measurements_user_location ON connectivity_measurements (user_id, latitude, longitude)',
    'SELECT ''idx_measurements_user_location already exists'''
);
PREPARE phase6_stmt FROM @phase6_sql;
EXECUTE phase6_stmt;
DEALLOCATE PREPARE phase6_stmt;
