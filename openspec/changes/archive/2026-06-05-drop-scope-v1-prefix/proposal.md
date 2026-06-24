## Why

当前运行时 scope 标识采用 `scope.v1.<tenant_b64>.<source_b64>` 格式，
其中 `scope.v1.` 只是格式前缀，不承载实际隔离信息，却让本地目录名、
Provider 目录名、日志和排查路径都更冗长。现在 source-scoped runtime
隔离已经稳定，继续保留该前缀的收益很低，反而增加理解和运维成本。

## What Changes

- 将运行时 `scope_id` 的标准格式从
  `scope.v1.<tenant_b64>.<source_b64>` 调整为
  `<tenant_b64>.<source_b64>`。
- 保持 `tenant_id + source_id` 作为唯一运行时隔离单元，不改变现有
  source-scoped runtime isolation 语义。
- 更新 scope 编码、解码、校验与路径解析逻辑，使其统一识别新格式。
- 更新 tenant 工作目录、Provider 目录、临时状态 key、日志与调试文案，
  统一使用去前缀后的 `scope_id`。
- **BREAKING** 停止生成新的 `scope.v1.*` 目录与 key；任何依赖旧前缀的
  本地脚本、调试工具、测试断言和人工运维约定都需要同步更新。
- **BREAKING** 明确旧格式仅作为迁移期兼容输入是否保留由实现阶段决定；
  默认目标是完成切换后内部标准表示只保留新格式。

## Capabilities

### New Capabilities
- `runtime-scope-id-format`: 定义运行时 scope 标识的无前缀编码格式、
  兼容边界与本地落盘规则。

### Modified Capabilities

## Impact

- Affected backend modules:
  - `src/swe/config/context.py`
  - `src/swe/config/utils.py`
  - `src/swe/app/middleware/tenant_identity.py`
  - `src/swe/app/workspace/*`
  - `src/swe/providers/provider_manager.py`
  - scope-aware routers, cron, callback, internal API, CLI entry points
- Affected local state:
  - `~/.swe/<scope>/`
  - `~/.swe.secret/<scope>/`
  - any scope-keyed transient stores, cache keys, logs, and diagnostics
- Affected tests and docs:
  - path assertions using `scope.v1.*`
  - tenant/source isolation analysis and playbooks
- Out of scope:
  - 不取消 `tenant_id + source_id` 的运行时隔离模型
  - 不回退到裸 `tenant_id` 目录作为 source-scoped runtime 主表示
