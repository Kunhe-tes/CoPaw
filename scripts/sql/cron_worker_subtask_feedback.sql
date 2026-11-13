-- 升级已有共库。发布 Scheduler 和 Monitor 前分别检查下列列名，
-- 只执行尚未存在的列。历史记录保留 NULL。
ALTER TABLE swe_cron_execution_runs ADD COLUMN subtask_success_count INT DEFAULT NULL;
ALTER TABLE swe_cron_execution_runs ADD COLUMN subtask_failure_count INT DEFAULT NULL;
ALTER TABLE swe_cron_dispatch_worker_capacity ADD COLUMN subtask_success_count INT DEFAULT NULL;
ALTER TABLE swe_cron_dispatch_worker_capacity ADD COLUMN subtask_failure_count INT DEFAULT NULL;
