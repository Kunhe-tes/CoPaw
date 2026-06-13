## Context

`source_id` 目前已经是运行时隔离身份的一部分：请求通过 `X-Source-Id` 进入 `TenantIdentityMiddleware`，并与逻辑 `tenant_id` 组合成 `scope_id`，后续 workspace、Provider、本地配置和临时状态按 `scope_id` 隔离。这个机制解决的是“同一用户在不同 source 下的数据不能混用”。

这次变化要解决另一个层面：每个 source 对应一个接入系统，系统管理员需要按 source 保存一份系统配置，并让请求进入运行时后能读取当前 source 的配置。由于部署为 Kubernetes 多实例，本地文件不是合适的 source 级系统配置存储；配置必须在实例之间共享。

## Goals / Non-Goals

**Goals:**

- 为每个 `source_id` 提供一份系统级配置，并支持增删改查。
- 请求进入后按当前 `source_id` 解析配置，并绑定到 `request.state` 与 ContextVar。
- Console 可从后端读取同一份 effective config，供后续页面按需消费。
- 不改变现有 tenant `config.json` 的职责，不把 source 系统策略写入用户/租户运行时配置。
- 在没有 source 配置的情况下保持现有系统默认行为，降低上线风险。

**Non-Goals:**

- 不支持 `bbk_id`、机构、用户、租户维度的 source 配置覆盖。
- 不做通用实验平台、灰度分流、百分比发布或人群规则。
- 不把所有现有配置项迁移到 source 系统配置。
- 不在本版为 Market、MCP、Skills、Agents、Provider、Hook、Analytics 等具体业务接口实现开关。
- 不规定具体开关 key；配置 JSON 的业务含义由后续开发人员在使用点自行决定。
- 不替代已有 source-scoped runtime isolation；该能力只叠加配置查询能力。

## Decisions

### 决策 1: 使用 MySQL 存储 source 系统配置

新增 `swe_source_system_config` 表，以 `source_id` 唯一保存 JSON 配置、版本和审计字段。

建议结构：

```sql
CREATE TABLE IF NOT EXISTS swe_source_system_config (
    source_id VARCHAR(64) NOT NULL,
    config_json JSON NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    updated_by VARCHAR(128) DEFAULT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (source_id)
);
```

理由：
- 多实例部署下所有实例都能读取同一份配置。
- JSON 字段便于后续新增任意 source 系统配置项，不需要每个配置项都做表结构变更。
- `version` 可用于前端缓存、后端本地缓存失效和并发更新保护。

备选方案：
- 写入 `~/.swe/<source>/config.json`：多实例一致性差，且容易和 tenant runtime config 混淆。
- 复用 tenant `config.json`：会把系统配置变成用户可变运行时状态，不适合作为 source 级系统配置。

### 决策 2: Source 配置按 source_id 直接生效

effective source 配置只由系统默认值和 source 配置合成：

```text
内置默认配置
  < source 配置
```

tenant/user 配置不能覆盖 source 系统配置。业务代码如果后续读取 source 配置做判断，应以当前 source 的配置为准。

理由：
- 符合“系统下的人运行时加载系统配置”的控制目标。
- 避免不同用户配置改变同一个 source 的系统级配置含义。

### 决策 3: 请求级绑定 effective config

新增 source config service 和运行时查询 helper：

```python
get_current_source_system_config()
```

SourceSystemConfigMiddleware 在身份解析后加载配置，并绑定到请求对象和 ContextVar。Console 或其他调用方可以通过 effective config API 主动查询当前 source 配置。

```text
HTTP request
  └─ X-Source-Id
      └─ TenantIdentityMiddleware
          └─ SourceSystemConfigMiddleware / dependency
              ├─ request.state.source_system_config
              └─ ContextVar

Console
  └─ GET /api/source-system-config/effective
      └─ store 保存当前 source effective config
```

理由：
- 后续业务接口可以在需要时读取同一份运行时配置。
- ContextVar 能复用于 HTTP、channel、cron 或内部执行路径。

### 决策 4: 配置内容保持泛化 JSON object

后端只要求 `config_json` 是 JSON object，不在本版注册或校验具体业务 key。开发人员可以在后续功能中约定并读取自己的配置项。

配置示例：

```json
{
  "provider_policy": {
    "default_model": "qwen-max"
  },
  "feature_switches": {
    "experimental_tooling": true
  }
}
```

理由：
- 本版只建设 source 配置基础设施，不提前决定具体开关。
- JSON object 结构便于后续业务模块逐步引入自己的 schema 和测试。

### 决策 5: 缓存采用短 TTL + version

Source config service 在进程内按 `source_id` 缓存解析后的配置，缓存项包含 `version`、加载时间和配置对象。

建议策略：
- 无配置记录：返回内置默认配置，保持当前行为。
- 配置记录存在但 JSON 无法解析或不是 object：记录错误并拒绝配置管理保存；运行时读取时优先使用 last known good cache。
- 数据库读取失败：若存在 last known good cache，则继续使用缓存；否则 effective config API 返回错误。
- 管理接口更新或删除成功后返回结果，当前实例立即刷新缓存；其他实例在 TTL 后自然刷新。

理由：
- 保持多实例一致性足够收敛，同时避免每个请求都打 DB。
- 区分“未配置 source”和“配置系统异常”，避免调用方误把存储异常当成空配置。

## Risks / Trade-offs

- [Risk] 泛化 JSON 可能让具体业务 key 缺少集中约束。→ Mitigation: 本版只提供基础设施；具体业务接入时应在对应模块补充 schema/helper 和测试。
- [Risk] 多实例更新不是立即全局生效。→ Mitigation: 使用短 TTL 和 version；如需要强一致，可后续引入 Redis pub/sub 或管理端刷新广播。
- [Risk] 配置 JSON 不是 object 会导致调用方语义不明确。→ Mitigation: 管理接口和存储解析只接受 JSON object。

## Migration Plan

1. 新增 `swe_source_system_config` 建表 SQL/migration。
2. 新增后端模型、store、service 和默认配置。
3. 新增 effective config 查询 API 和管理 API。
4. 在请求中间件中按当前 source 绑定 effective config。
5. Console 启动时加载 effective config，供后续页面按需消费。
6. 增加测试，确保未配置 source 返回默认配置，已配置 source 能被 CRUD 和请求级查询读取。

Rollback：
- 保留表不影响旧代码。
- 删除对应 source 的配置记录即可恢复默认空配置行为。

## Open Questions

- 后续哪些业务模块需要消费 source 系统配置，以及各自的 schema/helper 应放在哪个模块内。
