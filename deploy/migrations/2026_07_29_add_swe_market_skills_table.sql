-- 技能统计配置功能：市场技能表
-- 用于记录市场技能的统计配置

CREATE TABLE IF NOT EXISTS swe_marketplace_skills (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_id VARCHAR(64) NOT NULL COMMENT '应用入口标识',
    item_id VARCHAR(64) NOT NULL COMMENT '市场条目ID',
    skill_id VARCHAR(128) NOT NULL COMMENT '技能唯一标识符',
    skill_name VARCHAR(128) NOT NULL COMMENT '技能目录名',
    cn_name VARCHAR(256) DEFAULT '' COMMENT '中文展示名',
    include_in_statistics TINYINT(1) DEFAULT 1 COMMENT '是否纳入统计：1=纳入，0=不纳入',
    creator_id VARCHAR(64) DEFAULT '' COMMENT '创建人ID',
    creator_name VARCHAR(256) DEFAULT '' COMMENT '创建人名称',
    updator_id VARCHAR(64) DEFAULT '' COMMENT '更新人ID',
    updator_name VARCHAR(256) DEFAULT '' COMMENT '更新人名称',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_source_item (source_id, item_id),
    INDEX idx_skill_id (skill_id),
    INDEX idx_include_statistics (source_id, include_in_statistics),
    INDEX idx_creator_id (creator_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='市场技能表';