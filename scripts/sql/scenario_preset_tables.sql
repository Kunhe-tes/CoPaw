-- 场景预设目录表
-- 由部署或 DBA 显式执行；SWE 应用启动不会创建或迁移这些表。

CREATE TABLE IF NOT EXISTS swe_scenario_preset_nodes (
    id VARCHAR(64) PRIMARY KEY,
    source_id VARCHAR(64) NOT NULL,
    node_kind VARCHAR(16) NOT NULL,
    parent_id VARCHAR(64) NULL,
    parent_key VARCHAR(64) AS (IFNULL(parent_id, '')) STORED,
    name VARCHAR(128) NOT NULL,
    normalized_name VARCHAR(128) NOT NULL,
    prompt_draft TEXT NOT NULL,
    sort_order INT NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_scenario_preset_sibling_name
        (source_id, parent_key, normalized_name),
    KEY idx_scenario_preset_children (source_id, parent_id, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场景预设目录节点';

CREATE TABLE IF NOT EXISTS swe_scenario_preset_bindings (
    source_id VARCHAR(64) NOT NULL,
    scenario_id VARCHAR(64) NOT NULL,
    resource_id VARCHAR(128) NOT NULL,
    resource_type VARCHAR(16) NOT NULL,
    display_name VARCHAR(256) NOT NULL,
    sort_order INT NOT NULL,
    PRIMARY KEY (source_id, scenario_id, resource_type, resource_id),
    KEY idx_scenario_preset_bindings (source_id, scenario_id, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场景预设市场资源绑定';
