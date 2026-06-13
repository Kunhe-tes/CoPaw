## Context

当前运行时隔离已经统一到 `tenant_id + source_id` 这一层，但其本地
表示仍使用 `scope.v1.<tenant_b64>.<source_b64>`。该前缀主要用于早期
引入显式 scope 语义时避免与裸 tenant 目录混淆，现在目录层级已经明确：

- 裸 `default/` 与 `default_<source>/` 作为模板目录
- source-scoped runtime 使用独立 scope 目录

在此基础上，`scope.v1.` 前缀不再提供新的隔离能力，只增加目录长度、
日志噪音和人工排查成本。该变更横跨 context、路径解析、workspace、
providers、router、测试与本地目录迁移，属于一次跨模块格式收敛。

## Goals / Non-Goals

**Goals:**

- 将标准 `scope_id` 格式切换为 `<tenant_b64>.<source_b64>`
- 保留现有 source-scoped runtime isolation 语义不变
- 让编码、解码、路径解析、目录落盘、Provider 存储和临时 key 统一使用
  新格式
- 为本地已有 `scope.v1.*` 目录提供受控迁移路径，避免用户手工整理
- 为实现期提供清晰的兼容边界，避免新旧格式在进程内长期混用

**Non-Goals:**

- 不取消 `source_id` 参与运行时隔离
- 不把 source-scoped runtime 回退到裸 `tenant_id`
- 不修改 `default/`、`default_<source>/` 模板目录的命名语义
- 不引入新的数据库持久化模型来记录 scope 映射

## Decisions

### 1. 标准 `scope_id` 改为无前缀双段格式

运行时 canonical `scope_id` 统一定义为：

`<base64url(tenant_id)>.<base64url(source_id)>`

选择该格式的原因：

- 仍然保持可逆与 collision-safe
- 避免 tenant/source 原始值里的分隔符冲突
- 比 `scope.v1.*` 更短，且仍能通过“双段 base64url”特征识别为 scope

备选方案：

- 保留 `scope.v1.`：兼容性最好，但不能解决可读性与运维冗长问题
- 改成明文 `tenant.source`：可读性更强，但分隔符歧义和路径安全性更差

### 2. 解码与解析在迁移期兼容旧格式，但标准输出只产出新格式

`decode_scope_id()` 和相关 helper 需要同时识别：

- 新格式：`<tenant_b64>.<source_b64>`
- 旧格式：`scope.v1.<tenant_b64>.<source_b64>`

但 `encode_scope_id()`、`resolve_scope_id()`、`resolve_runtime_tenant_id()`
等标准输出只返回新格式。这样可以保证：

- 旧的输入、旧的 callback 参数、旧的缓存键在迁移期仍可被识别
- 新逻辑不会继续制造新的 `scope.v1.*`

备选方案：

- 完全拒绝旧格式：实现简单，但会放大本地目录和运行中任务的切换风险
- 长期双写新旧格式：兼容更强，但会让目录和缓存命名重新分叉

### 3. 本地目录迁移采用“按 scope 懒迁移”，而不是一次性全量扫描

对于 `~/.swe/<scope>` 与 `~/.swe.secret/<scope>`：

- 当代码解析出 canonical scope 后，若新目录不存在且旧目录存在，
  则执行一次迁移
- 迁移优先使用原子 rename；若跨设备或已有部分目标目录，则降级为受控
  copy/merge
- 迁移完成后，后续所有路径 helper 仅返回新目录

这样做的原因：

- 避免启动阶段全量扫描用户全部 tenant/source 目录
- 让迁移只发生在真正被访问的 scope 上
- 便于把迁移逻辑收敛到路径/初始化边界，而不是散落在业务层

备选方案：

- 启动时全量迁移：可一次性完成，但会扩大启动耗时与失败面
- 完全不迁移、仅新建目录：会导致旧数据无法直接被新格式命中

### 4. 进程内临时状态统一规范为 canonical scope key

所有 scope-aware 临时状态应只用 canonical 新格式作为 key，包括：

- workspace/runtime registry
- ProviderManager tenant key
- suggestions / approvals / MCP progress 等 transient store
- tracing、日志和调试文案里展示的运行时 scope

对于仍可能传入旧格式的位置，应在入口先 canonicalize，再进入具体 store。

备选方案：

- 让各 store 自行同时识别两种格式：局部改动小，但容易漏改并长期分叉

## Risks / Trade-offs

- [旧目录与新目录同时存在且内容不同] → 迁移逻辑需要定义冲突策略，并在
  发生 merge 时记录日志，避免静默覆盖
- [长生命周期后台任务仍持有旧 `scope_id`] → 入口统一 canonicalize，
  并在 rollout 时重启进程，减少旧 key 残留
- [测试与文档大量硬编码 `scope.v1`] → 在同一 change 中同步修正断言、
  分析文档和排查手册
- [无前缀格式可读性不如明文] → 保持可逆解码工具与调试文案，必要时在日志
  中同时打印原始 tenant/source

## Migration Plan

1. 修改 `context.py` 中 scope 编解码与识别逻辑，定义 canonical 新格式。
2. 修改所有路径 helper、workspace/provider 初始化和 transient store
   入口，在读写前先 canonicalize scope。
3. 在本地目录访问边界加入旧目录到新目录的懒迁移逻辑。
4. 更新 routers、CLI、internal API、callback 路径的测试与调试输出。
5. 更新分析文档、playbook 和目录示例。
6. rollout 时重启服务进程，避免进程内继续持有 tenant-only 或旧前缀 key。

Rollback:

- 若切换后发现严重兼容问题，可恢复旧版编码逻辑并继续识别原目录；
  但已经迁移到无前缀目录的数据需要通过兼容解析继续命中，不能依赖简单
  的代码回退后自动恢复原目录名。

## Open Questions

- 懒迁移遇到“新旧目录都存在且内容冲突”时，是否需要硬失败而不是 merge
- 对外暴露的调试 API / 管理接口是否需要明确展示 canonical scope 与
  decoded tenant/source 两组字段
