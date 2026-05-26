# -*- coding: utf-8 -*-
"""Database schema initialization for Monitor cron tables.

This module provides SQL scripts to create the required tables for
cron job definitions and execution history.
"""

import logging

from .connection import get_db_connection

logger = logging.getLogger(__name__)


# SQL for creating cron_jobs table
CREATE_CRON_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS swe_cron_jobs (
    id              VARCHAR(64) PRIMARY KEY COMMENT '任务ID (UUID)',
    name            VARCHAR(255) NOT NULL COMMENT '任务名称',
    tenant_id       VARCHAR(64) NOT NULL COMMENT '租户ID (分行号)',
    tenant_name     VARCHAR(255) DEFAULT '' COMMENT '租户姓名 (X-User-Name header)',
    bbk_id          VARCHAR(64) DEFAULT '' COMMENT '分行号 (X-Bbk-Id header)',
    source_id       VARCHAR(64) DEFAULT '' COMMENT '来源标识 (X-Source-Id header)',
    enabled         TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    task_type       VARCHAR(16) NOT NULL COMMENT '任务类型: text/agent',

    -- 调度配置
    cron_expr       VARCHAR(64) NOT NULL COMMENT 'cron表达式 (5字段)',
    timezone        VARCHAR(32) DEFAULT 'UTC' COMMENT '时区',

    -- 执行目标
    channel         VARCHAR(32) NOT NULL COMMENT '分发渠道',
    target_user_id  VARCHAR(64) DEFAULT '' COMMENT '目标用户ID',
    target_session_id VARCHAR(64) DEFAULT '' COMMENT '目标会话ID',

    -- 执行配置
    timeout_seconds INT DEFAULT 7200 COMMENT '超时秒数',
    max_concurrency INT DEFAULT 1 COMMENT '最大并发数',
    misfire_grace_seconds INT DEFAULT 300 COMMENT 'misfire容错秒数',

    -- 任务内容
    text_content    VARCHAR(4096) DEFAULT '' COMMENT 'text类型任务内容',
    request_input   VARCHAR(4096) DEFAULT '' COMMENT 'agent类型请求输入',

    -- 任务元数据
    creator_user_id VARCHAR(64) DEFAULT '' COMMENT '创建者用户ID',
    task_chat_id    VARCHAR(64) DEFAULT '' COMMENT '关联聊天ID',
    task_session_id VARCHAR(64) DEFAULT '' COMMENT '关联会话ID',
    meta            VARCHAR(4096) DEFAULT '' COMMENT '扩展元数据',

    -- 状态追踪
    status          VARCHAR(16) DEFAULT 'active' COMMENT '状态: active/paused/deleted',
    pause_reason    VARCHAR(32) DEFAULT '' COMMENT '暂停原因',

    -- 时间戳
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted_at      DATETIME DEFAULT NULL COMMENT '删除时间',

    INDEX idx_tenant_id (tenant_id),
    INDEX idx_bbk_id (bbk_id),
    INDEX idx_source_id (source_id),
    INDEX idx_creator_user_id (creator_user_id),
    INDEX idx_status (status),
    INDEX idx_enabled (enabled),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务定义表';
"""

# SQL for adding tenant_name column to existing table
ALTER_CRON_JOBS_ADD_TENANT_NAME = """
ALTER TABLE swe_cron_jobs
ADD COLUMN tenant_name VARCHAR(255) DEFAULT '' COMMENT '租户姓名 (X-User-Name header)'
AFTER tenant_id;
"""

# SQL for creating cron_executions table
CREATE_CRON_EXECUTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS swe_cron_executions (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '执行记录ID',
    job_id          VARCHAR(64) NOT NULL COMMENT '任务ID',
    job_name        VARCHAR(255) DEFAULT '' COMMENT '任务名称 (冗余存储便于查询)',
    tenant_id       VARCHAR(64) NOT NULL COMMENT '租户ID (分行号)',

    -- 执行时间
    scheduled_time  DATETIME DEFAULT NULL COMMENT '计划执行时间',
    actual_time     DATETIME NOT NULL COMMENT '实际开始时间',
    end_time        DATETIME DEFAULT NULL COMMENT '结束时间',
    duration_ms     INT DEFAULT 0 COMMENT '执行耗时 (毫秒)',

    -- 执行状态
    status          VARCHAR(16) NOT NULL COMMENT '状态: success/error/cancelled/timeout/skipped',
    error_message   VARCHAR(2048) DEFAULT '' COMMENT '错误信息',

    -- 执行上下文
    instance_id     VARCHAR(64) DEFAULT '' COMMENT '执行实例标识',
    executor_leader VARCHAR(64) DEFAULT '' COMMENT '执行者 leader ID',
    is_manual       TINYINT(1) DEFAULT 0 COMMENT '是否手动触发',

    -- 可追溯链路
    trace_id        VARCHAR(64) DEFAULT '' COMMENT '关联的 trace ID',
    session_id      VARCHAR(64) DEFAULT '' COMMENT '关联的 session ID',

    -- 执行结果预览
    input_snapshot  VARCHAR(2048) DEFAULT '' COMMENT '执行时的输入快照',
    output_preview  VARCHAR(512) DEFAULT '' COMMENT '输出预览 (前100字符)',

    -- 执行元数据
    meta            VARCHAR(2048) DEFAULT '' COMMENT '执行元数据',

    -- 时间戳
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',

    INDEX idx_job_id (job_id),
    INDEX idx_tenant_id (tenant_id),
    INDEX idx_status (status),
    INDEX idx_scheduled_time (scheduled_time),
    INDEX idx_actual_time (actual_time),
    INDEX idx_trace_id (trace_id),
    INDEX idx_tenant_actual (tenant_id, actual_time),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务执行历史表';
"""


# SQL for creating extracted customer names table
CREATE_EXTRACTED_CUSTOMER_NAMES_TABLE = """
CREATE TABLE IF NOT EXISTS swe_extracted_customer_names (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    trace_id        VARCHAR(64) NOT NULL COMMENT '关联的 trace ID',
    skill_name      VARCHAR(255) NOT NULL COMMENT '技能名称',
    user_message_names JSON NOT NULL COMMENT '用户消息中提取的姓名列表',
    model_output_names JSON NOT NULL COMMENT '模型输出中提取的姓名列表',
    user_id         VARCHAR(64) DEFAULT '' COMMENT '用户 ID',
    bbk_id          VARCHAR(64) DEFAULT '' COMMENT '分行 ID',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    UNIQUE INDEX uk_trace_skill (trace_id, skill_name),
    INDEX idx_skill_name (skill_name),
    INDEX idx_user_id (user_id),
    INDEX idx_bbk_id (bbk_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='提取客户姓名记录表';
"""


async def init_database_tables() -> None:
    """Initialize database tables for cron monitoring.

    Creates the cron_jobs, cron_executions, and extracted_customer_names
    tables if they don't exist.
    """
    db = get_db_connection()

    try:
        await db.execute(CREATE_CRON_JOBS_TABLE)
        logger.info("Created cron_jobs table (or already exists)")

        await db.execute(CREATE_CRON_EXECUTIONS_TABLE)
        logger.info("Created cron_executions table (or already exists)")

        await db.execute(CREATE_EXTRACTED_CUSTOMER_NAMES_TABLE)
        logger.info(
            "Created extracted_customer_names table (or already exists)",
        )

    except Exception as e:
        logger.error("Failed to initialize database tables: %s", e)
        raise
