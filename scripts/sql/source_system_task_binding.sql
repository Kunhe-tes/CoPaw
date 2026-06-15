CREATE TABLE IF NOT EXISTS swe_source_system_task_binding (
    source_id VARCHAR(64) NOT NULL,
    task_type VARCHAR(64) NOT NULL,
    external_job_id VARCHAR(191) NOT NULL,
    cron VARCHAR(64) NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    scheduler_tenant_id VARCHAR(64) DEFAULT NULL,
    scheduler_scope_id VARCHAR(128) DEFAULT NULL,
    scheduler_from_id VARCHAR(128) DEFAULT NULL,
    updated_by VARCHAR(128) DEFAULT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (source_id, task_type)
);
