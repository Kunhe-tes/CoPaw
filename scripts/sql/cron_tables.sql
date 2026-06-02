-- ============================================================
-- Cron Tables - 定时任务表定义
-- Date: 2026-05-18
-- Description: 创建定时任务相关表
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- -----------------------------------------------------------
-- 表: swe_cron_jobs (定时任务定义表)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `swe_cron_jobs` (
    `id` VARCHAR(64) PRIMARY KEY COMMENT '任务ID (UUID)',
    `name` VARCHAR(255) NOT NULL COMMENT '任务名称',
    `tenant_id` VARCHAR(64) NOT NULL COMMENT '租户ID (分行号)',
    `tenant_name` VARCHAR(255) DEFAULT '' COMMENT '租户姓名',
    `bbk_id` VARCHAR(64) DEFAULT '' COMMENT '分行号',
    `source_id` VARCHAR(64) DEFAULT '' COMMENT '来源标识',
    `enabled` TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    `task_type` VARCHAR(16) NOT NULL COMMENT '任务类型: text/agent',
    `cron_expr` VARCHAR(64) NOT NULL COMMENT 'cron表达式 (5字段)',
    `timezone` VARCHAR(32) DEFAULT 'UTC' COMMENT '时区',
    `channel` VARCHAR(32) NOT NULL COMMENT '分发渠道',
    `target_user_id` VARCHAR(64) DEFAULT '' COMMENT '目标用户ID',
    `target_session_id` VARCHAR(64) DEFAULT '' COMMENT '目标会话ID',
    `timeout_seconds` INT DEFAULT 7200 COMMENT '超时秒数',
    `max_concurrency` INT DEFAULT 1 COMMENT '最大并发数',
    `misfire_grace_seconds` INT DEFAULT 300 COMMENT 'misfire容错秒数',
    `text_content` VARCHAR(4096) DEFAULT '' COMMENT 'text类型任务内容',
    `request_input` VARCHAR(4096) DEFAULT '' COMMENT 'agent类型请求输入',
    `creator_user_id` VARCHAR(64) DEFAULT '' COMMENT '创建者用户ID',
    `task_chat_id` VARCHAR(64) DEFAULT '' COMMENT '关联聊天ID',
    `task_session_id` VARCHAR(64) DEFAULT '' COMMENT '关联会话ID',
    `meta` VARCHAR(4096) DEFAULT '' COMMENT '扩展元数据',
    `status` VARCHAR(16) DEFAULT 'active' COMMENT '状态: active/paused/deleted',
    `pause_reason` VARCHAR(32) DEFAULT '' COMMENT '暂停原因',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `deleted_at` DATETIME DEFAULT NULL COMMENT '删除时间',
    INDEX `idx_tenant_id` (`tenant_id`),
    INDEX `idx_bbk_id` (`bbk_id`),
    INDEX `idx_source_id` (`source_id`),
    INDEX `idx_creator_user_id` (`creator_user_id`),
    INDEX `idx_status` (`status`),
    INDEX `idx_enabled` (`enabled`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务定义表';

-- -----------------------------------------------------------
-- 表: swe_cron_executions (定时任务执行历史表)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `swe_cron_executions` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '执行记录ID',
    `job_id` VARCHAR(64) NOT NULL COMMENT '任务ID',
    `job_name` VARCHAR(255) DEFAULT '' COMMENT '任务名称',
    `tenant_id` VARCHAR(64) NOT NULL COMMENT '租户ID',
    `scheduled_time` DATETIME DEFAULT NULL COMMENT '计划执行时间',
    `actual_time` DATETIME NOT NULL COMMENT '实际开始时间',
    `end_time` DATETIME DEFAULT NULL COMMENT '结束时间',
    `duration_ms` INT DEFAULT 0 COMMENT '执行耗时 (毫秒)',
    `status` VARCHAR(16) NOT NULL COMMENT '状态: success/error/cancelled/timeout/skipped',
    `error_message` VARCHAR(2048) DEFAULT '' COMMENT '错误信息',
    `instance_id` VARCHAR(64) DEFAULT '' COMMENT '执行实例标识',
    `executor_leader` VARCHAR(64) DEFAULT '' COMMENT '执行者 leader ID',
    `is_manual` TINYINT(1) DEFAULT 0 COMMENT '是否手动触发',
    `trace_id` VARCHAR(64) DEFAULT '' COMMENT '关联的 trace ID',
    `session_id` VARCHAR(64) DEFAULT '' COMMENT '关联的 session ID',
    `input_snapshot` VARCHAR(2048) DEFAULT '' COMMENT '执行时的输入快照',
    `output_preview` VARCHAR(512) DEFAULT '' COMMENT '输出预览 (前100字符)',
    `meta` VARCHAR(2048) DEFAULT '' COMMENT '执行元数据',
    `notification_status` VARCHAR(16) DEFAULT 'not_required' COMMENT '通知状态',
    `notification_due_at` DATETIME DEFAULT NULL COMMENT '计划通知时间',
    `notification_timezone` VARCHAR(64) DEFAULT '' COMMENT '通知计算时区',
    `notification_sent_at` DATETIME DEFAULT NULL COMMENT '通知发送时间',
    `notification_attempts` INT DEFAULT 0 COMMENT '通知尝试次数',
    `notification_error` VARCHAR(2048) DEFAULT '' COMMENT '通知错误',
    `notification_lock_owner` VARCHAR(128) DEFAULT '' COMMENT '通知锁持有者',
    `notification_locked_at` DATETIME DEFAULT NULL COMMENT '通知锁时间',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    INDEX `idx_job_id` (`job_id`),
    INDEX `idx_tenant_id` (`tenant_id`),
    INDEX `idx_status` (`status`),
    INDEX `idx_scheduled_time` (`scheduled_time`),
    INDEX `idx_actual_time` (`actual_time`),
    INDEX `idx_trace_id` (`trace_id`),
    INDEX `idx_notification_scan` (`notification_status`, `notification_due_at`),
    INDEX `idx_notification_lock` (`notification_lock_owner`, `notification_locked_at`),
    INDEX `idx_tenant_actual` (`tenant_id`, `actual_time`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务执行历史表';

SET FOREIGN_KEY_CHECKS = 1;
