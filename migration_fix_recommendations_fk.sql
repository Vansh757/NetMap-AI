-- Migration: Fix connectivity_recommendations.user_id type mismatch and add Foreign Key
-- Run this on any existing netmap_db instance created before this fix.
-- Fully idempotent and safe to run multiple times.

USE netmap_db;

-- Step 1: Ensure users.id is INT UNSIGNED
SET @sql = IF(
    (SELECT COLUMN_TYPE FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'users'
       AND column_name = 'id') != 'int unsigned',
    'ALTER TABLE users MODIFY COLUMN id INT UNSIGNED NOT NULL AUTO_INCREMENT',
    'SELECT ''users.id is already INT UNSIGNED'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 2: Ensure connectivity_measurements.user_id is INT UNSIGNED
SET @sql = IF(
    (SELECT COLUMN_TYPE FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'connectivity_measurements'
       AND column_name = 'user_id') != 'int unsigned',
    'ALTER TABLE connectivity_measurements MODIFY COLUMN user_id INT UNSIGNED NOT NULL',
    'SELECT ''connectivity_measurements.user_id is already INT UNSIGNED'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 3: Temporarily drop indexes on recommendations only if user_id needs to be modified
SET @sql = IF(
    (SELECT COLUMN_TYPE FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'connectivity_recommendations'
       AND column_name = 'user_id') != 'int unsigned'
    AND (SELECT COUNT(*) FROM information_schema.statistics
         WHERE table_schema = DATABASE()
           AND table_name = 'connectivity_recommendations'
           AND index_name = 'uq_recommendations_user_fingerprint') > 0,
    'ALTER TABLE connectivity_recommendations DROP INDEX uq_recommendations_user_fingerprint, DROP INDEX idx_recommendations_user_status_seen',
    'SELECT ''Index drop not required'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 4: Ensure connectivity_recommendations.user_id is INT UNSIGNED and recreate indexes if dropped
SET @sql = IF(
    (SELECT COLUMN_TYPE FROM information_schema.columns
     WHERE table_schema = DATABASE()
       AND table_name = 'connectivity_recommendations'
       AND column_name = 'user_id') != 'int unsigned',
    'ALTER TABLE connectivity_recommendations MODIFY COLUMN user_id INT UNSIGNED NOT NULL, ADD UNIQUE KEY uq_recommendations_user_fingerprint (user_id, fingerprint), ADD KEY idx_recommendations_user_status_seen (user_id, status, last_seen)',
    'SELECT ''connectivity_recommendations.user_id is already INT UNSIGNED'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Step 5: Ensure FK constraint fk_recommendations_user exists
SET @sql = IF(
    (SELECT COUNT(*) FROM information_schema.referential_constraints
     WHERE constraint_schema = DATABASE()
       AND constraint_name = 'fk_recommendations_user') = 0,
    'ALTER TABLE connectivity_recommendations ADD CONSTRAINT fk_recommendations_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE',
    'SELECT ''fk_recommendations_user already exists, skipping'''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
