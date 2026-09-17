-- Add the upstream B3 trace identity to existing trace records.
-- Historical rows are not backfilled because their values cannot be classified reliably.
SET @b3_trace_column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'swe_tracing_traces'
      AND COLUMN_NAME = 'b3_trace_id'
);

SET @b3_trace_column_sql = IF(
    @b3_trace_column_exists = 0,
    'ALTER TABLE `swe_tracing_traces` ADD COLUMN `b3_trace_id` VARCHAR(64) DEFAULT NULL AFTER `trace_id`',
    'SELECT 1'
);

PREPARE b3_trace_column_stmt FROM @b3_trace_column_sql;
EXECUTE b3_trace_column_stmt;
DEALLOCATE PREPARE b3_trace_column_stmt;

SET @b3_trace_index_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'swe_tracing_traces'
      AND INDEX_NAME = 'idx_source_b3_trace'
);

SET @b3_trace_index_sql = IF(
    @b3_trace_index_exists = 0,
    'ALTER TABLE `swe_tracing_traces` ADD INDEX `idx_source_b3_trace` (`source_id`, `b3_trace_id`)',
    'SELECT 1'
);

PREPARE b3_trace_index_stmt FROM @b3_trace_index_sql;
EXECUTE b3_trace_index_stmt;
DEALLOCATE PREPARE b3_trace_index_stmt;
