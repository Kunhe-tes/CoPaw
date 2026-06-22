-- 技能注册表：存储 skill_id、cn_name 等字段
-- 用于跨系统同步和界面展示

CREATE TABLE IF NOT EXISTS swe_skills (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    skill_id VARCHAR(128) NOT NULL COMMENT '技能唯一标识符，跨租户共享',
    skill_name VARCHAR(128) NOT NULL COMMENT '技能目录名/运行时标识',
    cn_name VARCHAR(256) NOT NULL COMMENT '中文展示名',
    tenant_id VARCHAR(64) NOT NULL COMMENT '租户ID',
    tenant_name VARCHAR(256) DEFAULT '' COMMENT '租户名称',
    bbk_id VARCHAR(64) DEFAULT '' COMMENT 'BBK标识符',
    source VARCHAR(32) DEFAULT 'customized' COMMENT '来源：builtin/customized/marketplace',
    enabled TINYINT(1) DEFAULT 0 COMMENT '是否启用',
    description TEXT COMMENT '技能描述',
    version_text VARCHAR(32) DEFAULT '1.0.0' COMMENT '版本号',
    signature VARCHAR(64) DEFAULT '' COMMENT '内容哈希',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_skill_id_tenant (skill_id, tenant_id),
    INDEX idx_tenant_skill_name (tenant_id, skill_name),
    INDEX idx_tenant_enabled (tenant_id, enabled),
    INDEX idx_bbk_id (bbk_id),
    INDEX idx_source (source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='技能注册表';

-- 扩展追踪表：添加 skill_id 和 cn_name 字段
-- MySQL 不支持 ADD COLUMN IF NOT EXISTS，使用存储过程实现安全添加

DELIMITER //

DROP PROCEDURE IF EXISTS add_column_if_not_exists //

CREATE PROCEDURE add_column_if_not_exists()
BEGIN
    -- 添加 skill_id 字段
    IF NOT EXISTS (
        SELECT * FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = 'swe_tracing_spans'
        AND column_name = 'skill_id'
    ) THEN
        ALTER TABLE swe_tracing_spans
        ADD COLUMN skill_id VARCHAR(128) DEFAULT '' COMMENT '技能唯一标识符' AFTER skill_name;
    END IF;

    -- 添加 cn_name 字段
    IF NOT EXISTS (
        SELECT * FROM information_schema.columns
        WHERE table_schema = DATABASE()
        AND table_name = 'swe_tracing_spans'
        AND column_name = 'cn_name'
    ) THEN
        ALTER TABLE swe_tracing_spans
        ADD COLUMN cn_name VARCHAR(256) DEFAULT '' COMMENT '技能中文展示名' AFTER skill_id;
    END IF;

    -- 添加 skill_id 索引（如果不存在）
    IF NOT EXISTS (
        SELECT * FROM information_schema.statistics
        WHERE table_schema = DATABASE()
        AND table_name = 'swe_tracing_spans'
        AND index_name = 'idx_skill_id'
    ) THEN
        CREATE INDEX idx_skill_id ON swe_tracing_spans(skill_id);
    END IF;
END //

DELIMITER ;

-- 执行存储过程
CALL add_column_if_not_exists();

-- 清理存储过程
DROP PROCEDURE IF EXISTS add_column_if_not_exists;