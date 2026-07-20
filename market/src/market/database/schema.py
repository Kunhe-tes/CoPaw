# -*- coding: utf-8 -*-
"""Market 服务数据库表初始化。"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CREATE_ASYNC_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS swe_async_tasks (
    task_id VARCHAR(64) PRIMARY KEY COMMENT '异步任务ID',
    service VARCHAR(32) NOT NULL COMMENT '写入服务: swe/market',
    task_type VARCHAR(64) NOT NULL COMMENT '任务类型',
    status VARCHAR(32) NOT NULL COMMENT '任务状态',
    title VARCHAR(255) NOT NULL COMMENT '任务标题',
    summary VARCHAR(1024) DEFAULT NULL COMMENT '任务摘要',
    source_id VARCHAR(128) DEFAULT NULL COMMENT '来源标识',
    tenant_id VARCHAR(255) DEFAULT NULL COMMENT '租户ID',
    actor_user_id VARCHAR(255) DEFAULT NULL COMMENT '操作人ID',
    actor_user_name VARCHAR(255) DEFAULT NULL COMMENT '操作人名称',
    target_count INT NOT NULL DEFAULT 0 COMMENT '目标总数',
    done_count INT NOT NULL DEFAULT 0 COMMENT '完成数量',
    failed_count INT NOT NULL DEFAULT 0 COMMENT '失败数量',
    error_message TEXT DEFAULT NULL COMMENT '错误信息',
    result_json JSON DEFAULT NULL COMMENT '任务结果',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    finished_at DATETIME DEFAULT NULL COMMENT '完成时间',
    INDEX idx_async_tasks_status (status),
    INDEX idx_async_tasks_type (task_type),
    INDEX idx_async_tasks_source (source_id),
    INDEX idx_async_tasks_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='统一异步任务主表';
"""

CREATE_ASYNC_TASK_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS swe_async_task_items (
    task_id VARCHAR(64) NOT NULL COMMENT '异步任务ID',
    target_id VARCHAR(255) NOT NULL COMMENT '目标ID',
    target_name VARCHAR(255) DEFAULT NULL COMMENT '目标名称',
    status VARCHAR(32) NOT NULL COMMENT '目标执行状态',
    error_message TEXT DEFAULT NULL COMMENT '错误信息',
    result_json JSON DEFAULT NULL COMMENT '执行结果',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (task_id, target_id),
    INDEX idx_async_task_items_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='统一异步任务明细表';
"""


async def init_database_tables(db) -> None:
    """初始化 Market 需要的数据库表。"""
    await db.execute(CREATE_ASYNC_TASKS_TABLE)
    await db.execute(CREATE_ASYNC_TASK_ITEMS_TABLE)
    logger.info("Market async task tables initialized")
