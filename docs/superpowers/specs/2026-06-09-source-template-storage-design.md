# 多 source 模板租户存储语义设计文档

## 1. 设计目标

在不破坏现有普通租户 runtime scope 语义的前提下，引入统一的模板存储解析能力，使 `default + source` 在配置类操作中稳定落到 `default_{source}`，并确保分发、广播、Cron、Provider、Env 与运维查询保持一致。

## 2. 核心设计

### 2.1 双语义分层

系统内明确区分两层身份：

- **Runtime Identity**
  - 用于请求隔离、历史 scope 兼容、运行时任务执行
  - 继续以 `resolve_runtime_tenant_id()` 为核心

- **Storage Identity**
  - 用于目录、配置、Secrets、模板资产访问
  - 由新增统一 resolver 决定

这两者对普通租户通常一致，但在 `default + source` 时发生分叉：

- runtime identity：仍可保留历史 scope 兼容能力
- storage identity：固定为 `default_{source}`

### 2.2 统一 storage resolver

在 `src/swe/config/context.py` 中新增统一的 storage resolver，供以下链路复用：

- workspace 初始化
- path helpers
- ProviderManager
- Env/Secrets
- 运维分发入口
- Cron 配置访问

推荐接口：

- `resolve_storage_tenant_id(tenant_id, source_id, scope_id=None)`
- `resolve_storage_identity(...)`

### 2.3 路径层重构

当前 `config/utils.py` 中的路径 helper 默认偏 runtime 语义，会把普通 tenant 再次 scope 化。设计上需要拆分：

- runtime path helpers
- storage path helpers

重点是让已解析出的 `default_{source}` 不会再次被二次解析为新的 scope。

### 2.4 Workspace 主链

#### 模板态

- `default + source` 初始化时：
  - 若 `default_{source}` 不存在，则从 `default` 拷贝创建
  - 模板目录即配置目录
  - 不创建额外运行态目录

#### 普通租户

- 非 `default` 且带 `source` 时：
  - 继续使用 runtime scope 目录
  - 初始化模板来源为 `default_{source}`

### 2.5 配置资产归属

以下资产在模板态下统一归属 `default_{source}`：

- root `config.json`
- `workspaces/default/agent.json`
- Provider 配置
- Env 配置
- Skills 配置
- MCP 配置
- Channel 配置

### 2.6 运行态数据边界

模板不参与运行态数据隔离。第一阶段不要求模板拥有独立：

- `console_push_store`
- 渠道绑定
- 运行态任务记录

这样可以把模板角色收敛为“配置资产承载体”，避免与真实租户运行态耦合。

## 3. 模块设计

### 3.1 配置与路径层

涉及文件：

- `src/swe/config/context.py`
- `src/swe/config/utils.py`

改造目标：

- 新增 storage resolver
- 保留 runtime resolver 兼容语义
- 路径 helper 改为按场景选择 storage/runtime

### 3.2 Workspace 初始化层

涉及文件：

- `src/swe/app/workspace/tenant_initializer.py`
- `src/swe/app/workspace/tenant_pool.py`
- `src/swe/app/middleware/tenant_workspace.py`
- `src/swe/app/agent_context.py`

改造目标：

- `default + source` 命中 `default_{source}`
- 普通租户保持原 scope
- workspace、config、agent 读取路径保持一致

### 3.3 Provider / Env / Template Config

涉及文件：

- `src/swe/providers/provider_manager.py`
- `src/swe/app/routers/providers.py`
- `src/swe/app/routers/envs.py`
- `src/swe/app/routers/config.py`
- `src/swe/app/routers/skills.py`
- `src/swe/app/routers/mcp.py`

改造目标：

- 模板配置入口统一写入 `default_{source}`
- 普通租户运行态入口维持现有 runtime scope

### 3.4 Cron 兼容方案

涉及文件：

- `src/swe/app/crons/api.py`
- `src/swe/app/crons/executor.py`
- `src/swe/app/crons/manager.py`
- `src/swe/app/crons/coordination.py`
- `src/swe/app/crons/heartbeat.py`
- `src/swe/app/tenant_context.py`

约束：

- 不新增 Cron job 字段
- 保留 `tenant_id/source_id/scope_id`

设计策略：

- 创建 job 时仍保存现有字段
- 执行时引入统一 resolver
- 对 `default + source` 场景，配置访问走 storage 规则
- 对普通租户运行态执行，仍保留 runtime scope 规则

### 3.5 主表记录与运营视图

涉及文件：

- `src/swe/app/workspace/tenant_init_source_store.py`
- `src/swe/app/routers/user_info.py`

设计：

- 新增 `tenant_type`
- 模板记录使用 `tenant_type=template`
- 普通租户记录使用 `tenant_type=tenant`
- 默认查询只返回 `tenant`
- 超管视图可显式包含 `template`

### 3.6 备份恢复

涉及文件：

- `src/swe/app/backup/service.py`
- `src/swe/app/backup/worker.py`
- `src/swe/app/backup/shell_service.py`
- `src/swe/app/backup/shell_worker.py`

设计：

- 模板目录进入备份恢复范围
- 不单独排除 `default_{source}`

## 4. 兼容策略

### 4.1 历史目录兼容

- 读取阶段兼容历史 scope 目录
- 新写入逐步收敛到新规则
- 不做第一阶段强制迁移

### 4.2 历史 DB 兼容

- 旧记录保留
- 新增 `tenant_type`
- 查询层先过滤，再逐步治理历史数据

### 4.3 风险控制

最大风险是同一组 `(tenant_id, source_id)` 在不同链路上落到不同目录。设计上要求所有会决定持久化位置的入口统一复用 storage resolver，避免“局部修补”。

## 5. 测试设计

需要覆盖以下回归点：

1. `default + source -> default_{source}`
2. 非 default + source 仍走 scope
3. workspace / config / agent / provider / env / skills / mcp / channel 命中同一目录
4. Cron 广播创建后仍可正常执行
5. `tenant_type=template` 默认不进入运营视图
6. 模板目录可参与 backup/restore
7. 控制台 channel 默认值不再误判为 `false`

## 6. 方案收益

- 消除模板目录与 runtime scope 目录分裂
- 让模板配置能力语义清晰
- 为后续历史数据迁移保留兼容路径
- 降低运维分发、Cron、Provider、Env 的隐式错写风险
