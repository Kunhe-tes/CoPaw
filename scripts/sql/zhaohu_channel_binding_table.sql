-- ============================================================
-- 招乎渠道绑定表
-- 持久化 (tenant_id, source_id) → (robot_id, open_id) 映射
-- 支持配置更新时保存、推送时 robotId 查询、已有账户读取
-- ============================================================

CREATE TABLE IF NOT EXISTS swe_zhaohu_channel_binding (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL COMMENT '租户ID（即用户sapId）',
    source_id VARCHAR(64) NOT NULL DEFAULT 'zhaohu' COMMENT '来源标识（招乎渠道为zhaohu）',
    robot_id VARCHAR(128) NOT NULL COMMENT '机器人openId（用于推送消息）',
    open_id VARCHAR(128) DEFAULT NULL COMMENT '用户招乎openId（来自回调消息，可能为空）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_tenant_source (tenant_id, source_id),
    INDEX idx_tenant_robot (tenant_id, robot_id),
    INDEX idx_open_id (open_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='招乎渠道绑定表';
