## Why

当前 `source_id` 已经参与运行时目录、Provider、本地状态和数据查询隔离，但 source 级系统配置仍缺少统一持久化入口。不同 source 对应不同接入系统，需要能够按 source 保存、读取和更新一份系统配置，并让请求进入运行时后可以查询到当前 source 的配置。

## What Changes

- 新增 source 级系统配置能力，以 `source_id` 为唯一配置维度，不引入 `bbk_id` 或机构级覆盖。
- 新增配置管理接口和持久化模型，管理员可创建、读取、更新、删除 source 系统配置。
- 新增 effective config 查询能力，请求进入后按当前 `source_id` 绑定配置到 `request.state` 与运行时 ContextVar。
- 新增缓存与版本失效策略，兼顾 Kubernetes 多实例读取一致性和运行时性能。
- 保持 tenant `config.json` 作为用户/租户运行时配置，不把 source 系统策略写入 tenant 配置文件。
- 本版不针对任何具体业务接口实现开关，也不规定具体开关 key；配置内容由后续业务开发自行解释。

## Capabilities

### New Capabilities

- `source-system-config`: 管理和加载 source 级系统配置，并在请求运行时提供查询入口。

### Modified Capabilities

- None.

## Impact

- 后端：
  - 新增 source 系统配置模型、存储、服务、请求级加载上下文和管理 API。
  - 新增 SQL migration/table 初始化脚本。
- Console：
  - 新增 source effective config 拉取与前端状态存储，供后续页面按需消费。
- 测试：
  - 新增配置存储、默认值、缓存、请求绑定、管理 API 和 Console 加载的单元测试。
