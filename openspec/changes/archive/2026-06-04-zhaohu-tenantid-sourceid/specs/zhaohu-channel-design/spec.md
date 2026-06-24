## MODIFIED Requirements

### Requirement: Zhaohu channel callback SHALL persist binding info on every inbound message
系统 SHALL 在处理招乎回调消息时，自动将 tenant_id、source_id、robot_id、open_id 信息 upsert 到数据库。

#### Scenario: Callback with valid identity info persists binding
- **WHEN** 招乎渠道收到回调消息且解析出 tenant_id、source_id、robot_id、open_id
- **THEN** 系统 SHALL 调用 ZhaohuChannelBindingStore.upsert_binding() 持久化绑定信息
- **AND** 持久化失败时不影响消息正常处理流程

#### Scenario: Callback with missing identity info skips persist
- **WHEN** 招乎渠道收到回调消息但缺少 tenant_id 或 source_id
- **THEN** 系统 NOT 调用 upsert_binding
- **AND** 消息正常处理

### Requirement: Zhaohu channel push SHALL support reading robot_id from DB for cross-tenant scenarios
系统 SHALL 在推送消息时支持从数据库读取 robot_id，作为内存配置的补充。

#### Scenario: Push uses in-memory robot_open_id when available
- **WHEN** 推送消息且 self.robot_open_id 非空
- **THEN** 使用内存中的 robot_open_id 构建推送 payload

#### Scenario: Push falls back to DB robot_id when in-memory not available
- **WHEN** 推送消息且 self.robot_open_id 为空
- **AND** 数据库中存在对应 tenant_id+source_id 的绑定记录
- **THEN** 使用数据库中的 robot_id 构建推送 payload

#### Scenario: Push with no robot_id available
- **WHEN** 推送消息且 self.robot_open_id 为空且数据库中也无记录
- **THEN** 使用现有逻辑处理（可能使用空值或跳过推送）

### Requirement: Zhaohu channel SHALL initialize binding store on startup
系统 SHALL 在招乎渠道初始化时同步初始化 ZhaohuChannelBindingStore。

#### Scenario: Channel init with DB available
- **WHEN** ZhaohuChannel 实例化且数据库连接可用
- **THEN** 调用 init_zhaohu_binding_module(db) 初始化 Store

#### Scenario: Channel init without DB
- **WHEN** ZhaohuChannel 实例化且数据库连接不可用
- **THEN** 调用 init_zhaohu_binding_module(None)
- **AND** 渠道正常运行，绑定信息不落库
