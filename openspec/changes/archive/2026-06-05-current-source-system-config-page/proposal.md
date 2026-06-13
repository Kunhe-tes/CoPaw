## Why

当前已经有 source 级 effective config 的运行时加载能力，但 Console 仍缺少一个仅针对当前 iframe/source 上下文的系统配置入口。管理员无法在不暴露跨 source 编辑能力的前提下，为当前接入系统配置显式开关，也无法区分“继承默认值”和“当前 source 有显式覆盖”。

随着 `task_progress` 步骤条需要按 `source_id` 独立开关，单纯依赖前端读取 effective config 已经不够：页面需要读写当前 source 的原始配置，运行时也需要把该开关解释为完整能力开关，而不只是隐藏前端 UI。

## What Changes

- 为当前请求 `source_id` 新增 raw source config API：`GET /api/source-system-config/current`、`PUT /api/source-system-config/current`、`DELETE /api/source-system-config/current`，与现有 effective config API 分离。
- 在 `system-config-page` 新增“当前 source 系统配置”页面，只允许编辑当前 iframe/source 上下文，不提供 source 选择器，也不允许通过前端切换到其他 source。
- 在页面中引入受代码注册的 feature switch 表单，首个开关为 `feature_switches.chat_task_progress_enabled`。
- 保存注册开关时保留未知配置键，仅更新受管理字段；当保存值与默认值相同，或裁剪后配置为空时，自动回退为默认状态并删除显式记录。
- 保存或删除成功后刷新前端 effective source config store，使聊天页在当前 source 下无需整页刷新即可获得新配置。
- 将 `feature_switches.chat_task_progress_enabled` 定义为完整能力开关：关闭后系统提示词不再要求 `update_task_progress`，工具调用不再持久化进度，流式事件不再附带步骤条数据，前端也不再渲染步骤条。
- 规范当前 source 配置页的权限模型：仅 `manager`/`admin` 可以进入和编辑，前端需要补齐 `X-User-Role` 请求头映射与 403 态处理。

## Capabilities

### New Capabilities
- `current-source-system-config-page`: 为当前 iframe/source 上下文提供受控的 source 系统配置页面、原始配置接口和按 source 生效的特性开关能力。

### Modified Capabilities
- None.

## Impact

- 后端：
  - `src/swe/app/source_system_config/*` 需要新增 current-source raw config API 与默认值裁剪逻辑。
  - `src/swe/agents/react_agent.py`、`src/swe/agents/tools/update_task_progress.py`、`src/swe/app/runner/*` 需要接入 `chat_task_progress_enabled` 的运行时判定。
- Console：
  - `console/src/api/modules/sourceSystemConfig.ts`、`console/src/stores/sourceSystemConfigStore.ts` 需要扩展 current-source 读写能力与 effective config 刷新。
  - `system-config-page` 相关页面、路由和权限展示需要接入当前 source 配置页与开关表单。
  - `console/src/api/authHeaders.ts` 需要发送 `X-User-Role`。
- 测试：
  - 需要补充 raw config API、默认值裁剪、权限、前端保存刷新，以及 task progress 开关的前后端行为测试。
