## Why

招乎渠道当前缺少渠道信息的数据库持久化机制。`tenantId`（sapId）、`sourceId`、`robotId`（robot_open_id）等关键身份信息仅在内存中流转，无法支持以下场景：
1. **openId 变更追踪**：用户 openId 可能变更，需要记录历史关联关系
2. **分发推送时的身份解析**：推送消息需要根据 tenantId + sourceId 查找对应的 robotId
3. **已有账户读取**：需要根据 tenantId + sourceId 唯一标识账户，冲突时更新而非重复创建

## What Changes

- 新增数据库表 `swe_zhaohu_channel_binding`，存储招乎渠道绑定信息
- 新增 `ZhaohuChannelBindingStore` 数据库存储类，实现 CRUD 和 upsert 操作
- 在招乎渠道回调处理流程中，增加渠道绑定信息的落库逻辑
- 在消息推送流程中，支持从数据库读取 robotId 用于推送
- 支持根据 `(tenant_id, source_id)` 唯一键进行 upsert（冲突时更新）

## Capabilities

### New Capabilities

- `zhaohu-channel-binding-store`: 招乎渠道绑定信息数据库存储，支持 tenantId + sourceId 唯一性约束和 upsert 操作

### Modified Capabilities

- `zhaohu-channel-design`: 新增渠道绑定信息持久化需求，在回调处理和推送流程中集成数据库读写

## Impact

- **数据库**：新增 `swe_zhaohu_channel_binding` 表，需要数据库迁移
- **招乎频道**：`ZhaohuChannel` 类需要集成新的 Store，在回调处理时落库
- **推送流程**：`send()` 和 `_build_push_payload()` 方法可能需要从数据库读取 robotId
- **路由器**：`routers/zhaohu.py` 回调处理流程需要触发绑定信息存储
