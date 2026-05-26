-- ============================================================
-- Tracing Tables - 用于技能调用统计等追踪数据
-- Date: 2026-05-11
-- Description: 创建 swe_tracing_traces 和 swe_tracing_spans 表
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- -----------------------------------------------------------
-- 表: swe_tracing_traces
-- 说明: 追踪记录表，存储请求级别的追踪数据
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `swe_tracing_traces` (
    `id` BIGINT AUTO_INCREMENT COMMENT '自增主键',
    `trace_id` VARCHAR(36) NOT NULL COMMENT '追踪唯一标识，UUID格式',
    `source_id` VARCHAR(64) NOT NULL COMMENT '数据源标识，用于多租户数据隔离',
    `user_id` VARCHAR(128) DEFAULT NULL COMMENT '用户标识，发起请求的用户ID',
    `user_name` VARCHAR(256) DEFAULT NULL COMMENT '用户名称',
    `bbk_id` VARCHAR(64) DEFAULT NULL COMMENT 'BBK标识符',
    `session_id` VARCHAR(36) DEFAULT NULL COMMENT '会话标识，同一会话的多次请求共享此ID',
    `session_name` VARCHAR(256) DEFAULT NULL COMMENT '会话名称（从第一条消息提取）',
    `channel` VARCHAR(32) DEFAULT NULL COMMENT '通道来源，如 console/webhook/api 等',
    `start_time` DATETIME DEFAULT NULL COMMENT '追踪开始时间，用户请求发起时刻',
    `end_time` DATETIME DEFAULT NULL COMMENT '追踪结束时间，请求完成时刻',
    `duration_ms` INT DEFAULT NULL COMMENT '总耗时（毫秒），从开始到结束的时长',
    `model_name` VARCHAR(64) DEFAULT NULL COMMENT '主要使用的模型名称，如 gpt-4/claude-3',
    `total_input_tokens` INT DEFAULT 0 COMMENT '输入Token总数，所有LLM调用的输入累计',
    `total_output_tokens` INT DEFAULT 0 COMMENT '输出Token总数，所有LLM调用的输出累计',
    `total_tokens` INT DEFAULT 0 COMMENT 'Token总数，等于输入+输出',
    `tools_used` JSON DEFAULT NULL COMMENT '使用的工具列表，JSON数组格式',
    `skills_used` JSON DEFAULT NULL COMMENT '使用的技能列表，JSON数组格式',
    `status` VARCHAR(16) DEFAULT 'running' COMMENT '追踪状态：running/completed/error/cancelled',
    `error` TEXT DEFAULT NULL COMMENT '错误信息，失败时记录的错误描述',
    `user_message` TEXT DEFAULT NULL COMMENT '用户输入消息，截断后的摘要内容',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_trace_id` (`trace_id`),
    INDEX `idx_source_id` (`source_id`),
    INDEX `idx_source_start_time` (`source_id`, `start_time`),
    INDEX `idx_source_user` (`source_id`, `user_id`),
    INDEX `idx_source_session` (`source_id`, `session_id`),
    INDEX `idx_start_time` (`start_time`),
    INDEX `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='追踪记录表';

-- -----------------------------------------------------------
-- 表: swe_tracing_spans
-- 说明: Span记录表，存储技能调用、工具调用等事件数据
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `swe_tracing_spans` (
    `id` BIGINT AUTO_INCREMENT COMMENT '自增主键',
    `span_id` VARCHAR(36) NOT NULL COMMENT 'Span唯一标识，UUID格式',
    `trace_id` VARCHAR(36) NOT NULL COMMENT '所属追踪ID，关联 swe_tracing_traces.trace_id',
    `source_id` VARCHAR(64) NOT NULL COMMENT '数据源标识，用于多租户数据隔离',
    `name` VARCHAR(128) DEFAULT NULL COMMENT 'Span名称/操作名称，如工具名或事件描述',
    `event_type` VARCHAR(32) NOT NULL COMMENT '事件类型：llm_input/llm_output/tool_call_start/tool_call_end/skill_invocation',
    `start_time` DATETIME NOT NULL COMMENT 'Span开始时间',
    `end_time` DATETIME DEFAULT NULL COMMENT 'Span结束时间',
    `duration_ms` INT DEFAULT NULL COMMENT '耗时（毫秒）',
    `user_id` VARCHAR(128) DEFAULT '' COMMENT '用户标识，冗余存储便于直接查询',
    `user_name` VARCHAR(256) DEFAULT NULL COMMENT '用户名称',
    `bbk_id` VARCHAR(64) DEFAULT NULL COMMENT 'BBK标识符',
    `session_id` VARCHAR(36) DEFAULT '' COMMENT '会话标识，冗余存储便于直接查询',
    `channel` VARCHAR(32) DEFAULT '' COMMENT '通道来源，冗余存储便于直接查询',
    `model_name` VARCHAR(64) DEFAULT NULL COMMENT '模型名称，仅LLM事件使用',
    `input_tokens` INT DEFAULT NULL COMMENT '输入Token数，仅LLM事件使用',
    `output_tokens` INT DEFAULT NULL COMMENT '输出Token数，仅LLM事件使用',
    `tool_name` VARCHAR(64) DEFAULT NULL COMMENT '工具名称，仅工具事件使用',
    `skill_name` VARCHAR(128) DEFAULT NULL COMMENT '技能名称，用于工具归属和技能事件',
    `skill_description` TEXT DEFAULT NULL COMMENT '技能描述，从 SKILL.md 的 description 字段读取',
    `mcp_server` VARCHAR(64) DEFAULT NULL COMMENT 'MCP服务器名，标识MCP工具来源',
    `tool_input` JSON DEFAULT NULL COMMENT '工具输入参数，脱敏后的JSON格式',
    `tool_output` TEXT DEFAULT NULL COMMENT '工具输出结果，截断后的摘要',
    `error` TEXT DEFAULT NULL COMMENT '错误信息，失败时记录',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_span_id` (`span_id`),
    INDEX `idx_trace_id` (`trace_id`),
    INDEX `idx_source_id` (`source_id`),
    INDEX `idx_source_start_time` (`source_id`, `start_time`),
    INDEX `idx_source_trace` (`source_id`, `trace_id`),
    INDEX `idx_source_user` (`source_id`, `user_id`),
    INDEX `idx_source_session` (`source_id`, `session_id`),
    INDEX `idx_source_skill` (`source_id`, `event_type`, `skill_name`),
    INDEX `idx_source_tool` (`source_id`, `event_type`, `tool_name`),
    INDEX `idx_event_type` (`event_type`),
    INDEX `idx_skill_name` (`skill_name`),
    INDEX `idx_mcp_server` (`mcp_server`),
    INDEX `idx_start_time` (`start_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Span记录表';

-- -----------------------------------------------------------
-- 表: swe_marketplace_operation_logs
-- 说明: 市场操作日志（发布/下架/分发）
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `swe_marketplace_operation_logs` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `source_id` VARCHAR(64) NOT NULL COMMENT '应用入口标识',
    `operator_id` VARCHAR(64) NOT NULL COMMENT '操作人用户ID',
    `operator_name` VARCHAR(256) DEFAULT NULL COMMENT '操作人用户名称',
    `operation` VARCHAR(32) NOT NULL COMMENT '操作类型：publish/unpublish/distribute',
    `item_type` VARCHAR(16) NOT NULL COMMENT '条目类型：skill/mcp',
    `item_id` VARCHAR(64) NOT NULL COMMENT '市场条目ID',
    `item_name` VARCHAR(256) DEFAULT NULL COMMENT '市场条目名称',
    `target_user_id` VARCHAR(64) DEFAULT NULL COMMENT '分发目标用户ID',
    `target_user_name` VARCHAR(256) DEFAULT NULL COMMENT '分发目标用户名称',
    `target_bbk_id` VARCHAR(64) DEFAULT NULL COMMENT '分发目标用户所属机构ID（快照）',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    INDEX `idx_source_id` (`source_id`),
    INDEX `idx_item_id` (`item_id`),
    INDEX `idx_target_user_id` (`target_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='市场操作日志';

-- -----------------------------------------------------------
-- 表: swe_user_item_operation_logs
-- 说明: 用户技能/MCP操作日志
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `swe_user_item_operation_logs` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `source_id` VARCHAR(64) NOT NULL COMMENT '应用入口标识',
    `operator_id` VARCHAR(128) NOT NULL COMMENT '操作用户ID',
    `operator_name` VARCHAR(256) DEFAULT NULL COMMENT '操作用户名称',
    `operation` VARCHAR(32) NOT NULL COMMENT '操作类型：upload/edit/delete',
    `item_type` VARCHAR(16) NOT NULL COMMENT '条目类型：skill/mcp',
    `item_id` VARCHAR(64) DEFAULT '' COMMENT '条目ID（可为空）',
    `item_name` VARCHAR(256) NOT NULL COMMENT '条目名称',
    `target_user_id` VARCHAR(128) DEFAULT NULL COMMENT '目标用户ID',
    `target_user_name` VARCHAR(256) DEFAULT NULL COMMENT '目标用户名称',
    `target_bbk_id` VARCHAR(64) DEFAULT NULL COMMENT '目标用户所属机构ID',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    INDEX `idx_source_id` (`source_id`),
    INDEX `idx_operator_id` (`operator_id`),
    INDEX `idx_item_type` (`item_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户技能/MCP操作日志';

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- 验证表是否创建成功
-- ============================================================
SHOW TABLES LIKE 'swe_%';