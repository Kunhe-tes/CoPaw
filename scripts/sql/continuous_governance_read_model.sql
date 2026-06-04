-- 持续治理管理侧数据库读模型。

CREATE TABLE IF NOT EXISTS `swe_continuous_governance_records` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `source_id` VARCHAR(128) NOT NULL,
    `target_user_id` VARCHAR(128) NOT NULL,
    `target_agent_id` VARCHAR(128) NOT NULL DEFAULT 'default',
    `record_id` VARCHAR(128) NOT NULL,
    `target_user_name` VARCHAR(255) DEFAULT NULL,
    `bbk_id` VARCHAR(255) DEFAULT NULL,
    `occurred_at` VARCHAR(64) NOT NULL,
    `trigger_type` VARCHAR(64) NOT NULL,
    `status` VARCHAR(64) NOT NULL,
    `model_used` VARCHAR(255) DEFAULT NULL,
    `input_tokens` INT NOT NULL DEFAULT 0,
    `output_tokens` INT NOT NULL DEFAULT 0,
    `files_optimized_json` JSON NOT NULL,
    `total_size_saved` BIGINT NOT NULL DEFAULT 0,
    `total_files_changed` INT NOT NULL DEFAULT 0,
    `duration_ms` BIGINT NOT NULL DEFAULT 0,
    `summary` TEXT,
    `error_text` TEXT,
    `rollback_timestamp` VARCHAR(64) DEFAULT NULL,
    `rollback_files_json` JSON NOT NULL,
    `raw_record_json` JSON NOT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_cg_record_identity` (
        `source_id`, `target_user_id`, `target_agent_id`, `record_id`
    ),
    KEY `idx_cg_records_source_time` (`source_id`, `occurred_at`),
    KEY `idx_cg_records_source_user` (`source_id`, `target_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `swe_file_governance_archive_items` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `source_id` VARCHAR(128) NOT NULL,
    `target_user_id` VARCHAR(128) NOT NULL,
    `target_agent_id` VARCHAR(128) NOT NULL DEFAULT 'default',
    `archive_item_id` VARCHAR(128) NOT NULL,
    `original_path` TEXT NOT NULL,
    `archive_path` TEXT NOT NULL,
    `size_bytes` BIGINT NOT NULL DEFAULT 0,
    `mtime` VARCHAR(64) NOT NULL,
    `archived_at` VARCHAR(64) NOT NULL,
    `archived_by` VARCHAR(255) NOT NULL,
    `archive_reason` VARCHAR(255) NOT NULL,
    `expired` TINYINT(1) NOT NULL DEFAULT 0,
    `raw_item_json` JSON NOT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_fg_archive_identity` (
        `source_id`, `target_user_id`, `target_agent_id`, `archive_item_id`
    ),
    KEY `idx_fg_archive_source_time` (`source_id`, `archived_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `swe_file_governance_protected_files` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `source_id` VARCHAR(128) NOT NULL,
    `target_user_id` VARCHAR(128) NOT NULL,
    `target_agent_id` VARCHAR(128) NOT NULL DEFAULT 'default',
    `path` VARCHAR(384) NOT NULL,
    `protected_at` VARCHAR(64) NOT NULL,
    `protected_by` VARCHAR(255) NOT NULL,
    `reason` VARCHAR(255) NOT NULL,
    `exists_flag` TINYINT(1) NOT NULL DEFAULT 0,
    `size_bytes` BIGINT DEFAULT NULL,
    `mtime` VARCHAR(64) DEFAULT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_fg_protected_identity` (
        `source_id`, `target_user_id`, `target_agent_id`, `path`
    ),
    KEY `idx_fg_protected_source` (`source_id`, `target_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `swe_file_governance_cleanup_audits` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `event_id` VARCHAR(128) NOT NULL,
    `occurred_at` VARCHAR(64) NOT NULL,
    `operation` VARCHAR(128) NOT NULL,
    `status` VARCHAR(64) NOT NULL,
    `actor_user_id` VARCHAR(255) NOT NULL,
    `actor_role` VARCHAR(64) NOT NULL,
    `source_id` VARCHAR(128) NOT NULL,
    `source_name` VARCHAR(255) DEFAULT NULL,
    `target_user_id` VARCHAR(128) NOT NULL,
    `target_agent_id` VARCHAR(128) NOT NULL DEFAULT 'default',
    `scope` VARCHAR(128) NOT NULL,
    `files_count` INT NOT NULL DEFAULT 0,
    `total_size_bytes` BIGINT NOT NULL DEFAULT 0,
    `reason` VARCHAR(255) NOT NULL,
    `error_text` TEXT,
    `raw_audit_json` JSON NOT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_fg_cleanup_audit_event` (`source_id`, `event_id`),
    KEY `idx_fg_cleanup_source_time` (`source_id`, `occurred_at`),
    KEY `idx_fg_cleanup_source_user` (`source_id`, `target_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `swe_continuous_governance_reconcile_health` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `source_id` VARCHAR(128) NOT NULL,
    `target_user_id` VARCHAR(128) NOT NULL,
    `target_agent_id` VARCHAR(128) NOT NULL DEFAULT 'default',
    `entity_type` VARCHAR(128) NOT NULL,
    `entity_id` VARCHAR(128) NOT NULL,
    `status` VARCHAR(64) NOT NULL,
    `reason` VARCHAR(255) NOT NULL,
    `error_text` TEXT,
    `payload_json` JSON NOT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_cg_health_entity` (
        `source_id`, `target_user_id`, `target_agent_id`,
        `entity_type`, `entity_id`
    ),
    KEY `idx_cg_health_source_status` (`source_id`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
