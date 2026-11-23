-- 已有库在升级 Scheduler 前手工执行；字段已存在时跳过对应语句。
ALTER TABLE swe_cron_dispatch_intents
    ADD COLUMN worker_feedback_attempt INT DEFAULT NULL COMMENT '已计入 Worker 容量决策的执行轮次';
ALTER TABLE swe_cron_dispatch_events
    ADD COLUMN worker_feedback_used TINYINT NOT NULL DEFAULT 0 COMMENT '是否已计入 Worker 容量决策';
-- 仅使用旧版派发且没有此表的环境跳过此语句。
ALTER TABLE swe_cron_execution_runs
    ADD COLUMN worker_feedback_used TINYINT NOT NULL DEFAULT 0 COMMENT '是否已计入 Worker 容量决策';
