# 多 source 模板租户存储语义需求文档

## 1. 背景

当前项目已经同时存在两套租户语义：

- 运行时语义：`tenant_id + source_id -> scope_id`
- 模板语义：`default + source_id -> default_{source}`

现状中，这两套语义混杂在初始化、请求访问、配置分发、Provider、Env、Cron 广播、运维查询等多个链路中，导致以下问题：

- 初始化目录与请求实际访问目录可能不一致
- `default_{source}` 模板目录与 runtime scope 目录可能发生分裂
- Provider、Env、Channel、Skill、MCP 等配置可能写入不同目录
- Cron 广播创建与执行阶段可能命中不同目录
- 运维主表中的模板记录与真实租户记录混用，污染运营视图

## 2. 目标

本次改造的目标是统一“模板配置存储语义”，确保在 `source_id` 场景下：

1. `default + source_id` 的模板目录统一为 `default_{source}`
2. 普通租户继续使用现有 runtime scope 目录策略
3. 模板态配置能力统一落在 `default_{source}` 目录
4. 运行态数据不落在模板目录
5. 分发、广播、Cron、运维查询对模板与普通租户保持一致语义

## 3. 需求范围

### 3.1 存储身份规则

系统需要区分两类身份：

- 运行时身份：用于请求隔离、历史 scope 兼容、运行态任务执行
- 存储身份：用于目录、配置、Secrets、模板资产访问

存储身份规则如下：

- historical scope：兼容读取，保留 canonicalize 能力
- `default + no source`：存储目录为 `default`
- `default + source`：存储目录为 `default_{source}`
- `non-default + source`：保持现有 runtime scope 目录
- `non-default + no source`：保持原样

### 3.2 模板目录规则

- `default_{source}` 是该 `source` 的唯一模板目录
- 模板目录支持以下配置资产维护：
  - Provider
  - MCP
  - Skills
  - Channel
  - Env
- 模板目录应作为新租户初始化的来源目录

### 3.3 default 用户运行态规则

- `default + source` 不创建单独运行态目录
- 模板只承载配置，不参与运行态数据
- 下列运行态数据不要求模板隔离：
  - `console_push_store`
  - 渠道绑定
  - 运行态任务记录

### 3.4 普通租户初始化规则

- 新的 `source_id` 首次初始化时：
  - 若租户为 `default`，使用 `default` 初始化 `default_{source}`
  - 若租户非 `default`，先确保 `default_{source}` 存在，再使用它初始化普通租户目录
- 已存在的 `source_id` 下新增普通租户时：
  - 使用 `default_{source}` 初始化租户目录

### 3.5 配置读写一致性

下列能力在模板态下都必须访问 `default_{source}`：

- `config.json`
- `workspaces/default/agent.json`
- Provider 配置
- Env 配置
- Skills 配置
- MCP 配置
- Channel 配置

### 3.6 分发与广播一致性

所有面向租户的同步分发、广播、批量写入、异步调度需要遵守统一规则：

- 模板态操作命中 `default_{source}`
- 普通租户运行态操作维持原 scope 语义

涵盖范围包括：

- Channel 分发
- Agent 配置分发
- Provider 分发
- Active model 分发
- Skills 广播
- MCP 广播
- Workspace 文件广播
- Env 目标写入
- Cron 广播及执行
- Backup/Restore

### 3.7 Cron 规则

- 不新增 Cron job 的持久化字段结构
- 继续保留现有：
  - `tenant_id`
  - `source_id`
  - `scope_id`
- 但创建和执行时必须通过统一 resolver 兼容新模板规则
- 需保证 Cron 广播后的任务仍可正常执行

### 3.8 数据库记录规则

`swe_tenant_init_source` 需要支持区分模板与真实租户：

- 新增字段：`tenant_type`
- 建议值：
  - `tenant`
  - `template`

写入规则：

- `default_{source}` 模板记录写入主表
- 模板记录默认仅超级管理员可见
- 普通运营查询默认隐藏模板记录

### 3.9 历史数据兼容

- 先兼容读取历史 scope 目录
- 暂不做强制迁移
- 历史 DB 记录先保留
- 后续再单独治理历史数据迁移

### 3.10 备份恢复规则

- 模板目录纳入 backup / restore 范围

## 4. 非目标

本次不处理以下事项：

- 立即迁移所有历史 scope 目录到 `default_{source}`
- 重构所有运行态渠道绑定模型
- 修改模板用户的运行态 console/渠道行为
- 对所有历史 DB 记录做一次性清洗

## 5. 成功标准

满足以下条件视为需求达成：

1. `default + source` 模板访问统一命中 `default_{source}`
2. 普通租户继续命中原 runtime scope 目录
3. Provider / Env / Config / Agent / Skills / MCP / Channel 不再出现目录分裂
4. Cron 广播与执行链在新规则下仍正常运行
5. 运营视图默认不展示模板记录
6. 模板目录可被备份与恢复
