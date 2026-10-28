-- 当日失败补跑：请在 SWE / Scheduler / Monitor 共用数据库人工执行。
-- 应用启动不会执行此 DDL；不修改 swe_cron_executions 的列结构。
-- 时间字段以 UTC 保存，business_date 为北京时间自然日。
CREATE TABLE IF NOT EXISTS swe_cron_failure_retry_calls (
    call_id CHAR(36) COLLATE utf8mb4_bin NOT NULL COMMENT '接口调用批次标识',
    source_id VARCHAR(128) COLLATE utf8mb4_bin NOT NULL COMMENT '扫描来源标识',
    business_date DATE NOT NULL COMMENT '北京时间扫描日期',
    window_start DATETIME(6) NOT NULL COMMENT '扫描起始时刻（UTC）',
    cutoff_at DATETIME(6) NOT NULL COMMENT '受理时固定的扫描截止时刻（UTC）',
    max_queue_order BIGINT UNSIGNED NOT NULL COMMENT '受理时执行队列高水位',
    queue_cursor BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已处理执行队列游标',
    status VARCHAR(32) NOT NULL COMMENT '扫描处理状态，不代表业务执行完成',
    scanned_count BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已检查失败记录数',
    queued_count BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已受理补跑数量',
    skipped_count BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已跳过数量',
    failed_count BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '逐项处理异常数量',
    error_code VARCHAR(128) NULL COMMENT '批次最近错误码（脱敏）',
    lease_owner CHAR(36) NOT NULL DEFAULT '' COMMENT '当前处理实例租约令牌',
    lease_until DATETIME(6) NULL COMMENT '处理租约截止时刻（UTC）',
    version BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '乐观版本号',
    created_at DATETIME(6) NOT NULL COMMENT '请求受理时间（UTC）',
    started_at DATETIME(6) NULL COMMENT '首次开始扫描时间（UTC）',
    finished_at DATETIME(6) NULL COMMENT '扫描处理结束时间（UTC）',
    updated_at DATETIME(6) NOT NULL COMMENT '最后更新时间（UTC）',
    PRIMARY KEY (call_id),
    KEY idx_failure_retry_recovery (status, lease_until, created_at),
    KEY idx_failure_retry_source (source_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
  COMMENT='新版定时任务当日失败补跑接口调用记录';
