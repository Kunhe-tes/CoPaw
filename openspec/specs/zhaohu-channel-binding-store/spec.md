## Requirements

### Requirement: Zhaohu channel binding table SHALL persist tenant-source-robot-openId mapping
系统 SHALL 在数据库中持久化招乎渠道绑定信息，包含 tenant_id、source_id、robot_id、open_id 四个核心字段。

#### Scenario: Table created with correct schema
- **WHEN** 数据库初始化执行建表语句
- **THEN** 创建 `swe_zhaohu_channel_binding` 表，包含列：id(BIGINT AUTO_INCREMENT PK)、tenant_id(VARCHAR 128 NOT NULL)、source_id(VARCHAR 64 NOT NULL DEFAULT 'zhaohu')、robot_id(VARCHAR 128 NOT NULL)、open_id(VARCHAR 128 NOT NULL)、created_at(TIMESTAMP)、updated_at(TIMESTAMP)
- **AND** 在 (tenant_id, source_id) 上建立唯一键 uk_tenant_source
- **AND** 在 open_id 上建立索引 idx_open_id

### Requirement: Store SHALL support upsert with conflict-on-update semantics
系统 SHALL 支持按 (tenant_id, source_id) 进行 upsert 操作，冲突时更新 robot_id 和 open_id。

#### Scenario: Insert new binding record
- **WHEN** 调用 upsert_binding(tenant_id, source_id, robot_id, open_id) 且 (tenant_id, source_id) 组合不存在
- **THEN** 系统插入新记录
- **AND** 返回 True

#### Scenario: Update existing binding on conflict
- **WHEN** 调用 upsert_binding(tenant_id, source_id, robot_id, open_id) 且 (tenant_id, source_id) 组合已存在
- **THEN** 系统更新 robot_id 和 open_id 为新值
- **AND** updated_at 自动更新为当前时间
- **AND** 返回 True

#### Scenario: Upsert when database unavailable
- **WHEN** 调用 upsert_binding 且数据库不可用
- **THEN** 系统 NOT 抛出异常
- **AND** 返回 False

### Requirement: Store SHALL support reading binding by tenant and source
系统 SHALL 支持按 (tenant_id, source_id) 查询绑定记录。

#### Scenario: Query existing binding
- **WHEN** 调用 get_binding(tenant_id, source_id) 且记录存在
- **THEN** 返回包含 robot_id、open_id、created_at、updated_at 的字典

#### Scenario: Query non-existent binding
- **WHEN** 调用 get_binding(tenant_id, source_id) 且记录不存在
- **THEN** 返回 None

#### Scenario: Query when database unavailable
- **WHEN** 调用 get_binding 且数据库不可用
- **THEN** 返回 None

### Requirement: Store SHALL support reading robot_id by tenant and source
系统 SHALL 提供便捷方法按 (tenant_id, source_id) 查询 robot_id。

#### Scenario: Get robot_id for existing binding
- **WHEN** 调用 get_robot_id(tenant_id, source_id) 且记录存在
- **THEN** 返回 robot_id 字符串

#### Scenario: Get robot_id for non-existent binding
- **WHEN** 调用 get_robot_id(tenant_id, source_id) 且记录不存在
- **THEN** 返回 None

### Requirement: Store SHALL support reading binding by open_id
系统 SHALL 支持按 open_id 查询绑定记录。

#### Scenario: Query binding by open_id
- **WHEN** 调用 get_binding_by_open_id(open_id) 且该 open_id 存在
- **THEN** 返回包含 tenant_id、source_id、robot_id、created_at、updated_at 的字典

#### Scenario: Query binding by non-existent open_id
- **WHEN** 调用 get_binding_by_open_id(open_id) 且该 open_id 不存在
- **THEN** 返回 None

### Requirement: Store SHALL use module-level singleton pattern
系统 SHALL 使用模块级单例模式初始化和获取 Store 实例。

#### Scenario: Initialize store with database connection
- **WHEN** 调用 init_zhaohu_binding_module(db) 且 db 连接可用
- **THEN** 创建 ZhaohuChannelBindingStore 实例并设为全局单例

#### Scenario: Initialize store without database connection
- **WHEN** 调用 init_zhaohu_binding_module(None) 或 db 连接不可用
- **THEN** 全局单例设为 None
- **AND** 后续调用 get_zhaohu_binding_store() 返回 None
