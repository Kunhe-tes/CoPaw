-- ============================================================
-- Migration: Add need_notification column
-- Date: 2026-07-16
-- Description: 添加通知需求标识字段到子任务和执行记录表
-- ============================================================

SET NAMES utf8mb4;

-- -----------------------------------------------------------
-- 表: swe_cron_subtasks 添加 need_notification 字段
-- -----------------------------------------------------------
ALTER TABLE swe_cron_subtasks
ADD COLUMN IF NOT EXISTS need_notification TINYINT(1) DEFAULT 1
COMMENT '是否需要通知: 0-否, 1-是'
AFTER notification_content_zhaohu;

-- -----------------------------------------------------------
-- 表: swe_cron_executions 添加 need_notification 字段
-- -----------------------------------------------------------
ALTER TABLE swe_cron_executions
ADD COLUMN IF NOT EXISTS need_notification TINYINT(1) DEFAULT 1
COMMENT '是否需要通知: 0-否, 1-是'
AFTER async_status;