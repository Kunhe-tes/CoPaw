## Context

招乎渠道当前的身份信息（tenantId/sourceId/robotId/openId）仅在内存中流转，回调处理时通过 API 实时查询获取，不落库。这导致：
1. 无法追踪 openId 变更历史
2. 推送时无法按 tenantId+sourceId 查找对应的 robotId
3. 无法持久化已有账户绑定关系

现有数据库层使用 raw SQL + aiomysql，无 ORM。`TenantInitSourceStore` 和 `SourceSystemConfigStore` 提供了可复用的 Store 模式。

## Goals / Non-Goals

**Goals:**
- 新建 `swe_zhaohu_channel_binding` 表，持久化 (tenant_id, source_id) → (robot_id, open_id) 映射
- (tenant_id, source_id) 唯一约束，冲突时更新 robot_id 和 open_id
- 在回调处理时自动 upsert 绑定信息（覆盖 openId 变更场景）
- 推送时支持从 DB 读取 robot_id（覆盖分发推送场景）
- 支持按 tenantId+sourceId 查询已有账户绑定（覆盖已有账户读取场景）
- DB 不可用时优雅降级，不影响现有渠道功能

**Non-Goals:**
- 不做 openId 变更的历史记录追踪（仅更新最新值）
- 不做批量推送场景的优化
- 不修改现有 `swe_tenant_init_source` 表结构
- 不引入 ORM 框架

## Decisions

### Decision 1: 使用 ON DUPLICATE KEY UPDATE 实现 upsert

**选择**: MySQL `ON DUPLICATE KEY UPDATE`
**替代方案**: 应用层 SELECT-then-INSERT/UPDATE（如 FeedbackStore 模式）
**理由**: 原子操作无竞态条件，代码更简洁，项目已有先例（SourceSystemConfigStore）。应用层 upsert 在并发场景下可能出现两次 INSERT 导致唯一键冲突。

### Decision 2: Store 使用模块级单例模式

**选择**: 模块级 `_store` + `init_*_module()` + `get_*_store()` 便捷函数
**替代方案**: 依赖注入到 ZhaohuChannel 构造函数
**理由**: 与 `TenantInitSourceStore` 保持一致，Channel 实例化路径复杂（from_env/from_config），单例模式避免穿透传递 db 连接。

### Decision 3: Store 文件放置在 zhaohu 目录下

**选择**: `src/swe/app/channels/zhaohu/binding_store.py`
**替代方案**: 放在 `src/swe/app/workspace/` 下
**理由**: 绑定信息是招乎渠道特有的，放在渠道目录下内聚性更好。如果未来其他渠道也需要类似机制，再考虑抽取公共层。

### Decision 4: 推送时优先使用内存中的 robot_open_id，DB 作为补充

**选择**: 推送时先使用 `self.robot_open_id`（内存配置），仅当需要跨租户 robotId 查询时才读 DB
**理由**: 当前每个 ZhaohuChannel 实例的 robot_open_id 来自配置，是权威来源。DB 存储的 robot_id 用于记录和跨场景查询，不应覆盖运行时配置值。

## Risks / Trade-offs

- **[Risk] DB 不可用时绑定信息丢失** → 优雅降级：Store 方法返回 None/False，渠道继续使用内存配置正常工作
- **[Risk] ON DUPLICATE KEY UPDATE 与 aiomysql 的兼容性** → 项目已有先例验证，风险低
- **[Trade-off] 单例模式不利于单元测试** → 提供 `init_*_module(db=None)` 接口，测试中可注入 mock DB
- **[Trade-off] 每次回调都 upsert 可能增加 DB 写入压力** → 单次 upsert 是轻量操作，且回调频率通常不高
