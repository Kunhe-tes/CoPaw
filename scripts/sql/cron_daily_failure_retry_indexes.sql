-- 在 SWE / Scheduler / Monitor 共用数据库人工执行；应用不会自动执行。
-- 先 SHOW INDEX FROM swe_cron_execution_runs；已有同名或等价索引时跳过对应语句。
-- MySQL 的 ADD INDEX 不支持通用 IF NOT EXISTS；不要重复执行。
-- 请按行内变更规范选择执行窗口，实际建索引锁行为由数据库版本及表规模决定。
ALTER TABLE swe_cron_execution_runs
    ADD INDEX idx_daily_retry_main (source_id, status, finished_at, queue_order)
    COMMENT '按来源和主执行失败时间扫描当日失败';

ALTER TABLE swe_cron_execution_runs
    ADD INDEX idx_daily_retry_settled (source_id, status, settled_status, settled_at, queue_order)
    COMMENT '按来源和异步失败收敛时间扫描当日失败';

ALTER TABLE swe_cron_execution_runs
    ADD INDEX idx_daily_retry_latest (tenant_id, source_id, agent_id, job_id, queue_order)
    COMMENT '按完整任务身份查询最新自动执行及补跑尝试';
