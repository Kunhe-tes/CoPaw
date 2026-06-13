## Context

当前 `source-system-config` 基础能力已经提供：

- source 级配置存储与 effective config 解析；
- `GET /api/source-system-config/effective` 供运行时和 Console 读取当前 source 的生效配置；
- manager/admin 通过 `/api/source-system-config/sources/{source_id}` 管理任意 source 的配置。

但这套能力仍然缺三块关键拼图：

1. Console 没有“只操作当前 iframe/source”的配置页，现有管理接口天然暴露跨 source 编辑语义；
2. effective config 是“默认值 + 覆盖值”的合成结果，不适合作为编辑页的回填数据源，因为页面需要区分默认值和显式覆盖；
3. `task_progress` 当前不是纯前端展示逻辑。Agent 系统提示词会要求模型调用 `update_task_progress`，工具会写入 tracker，runner 会把结果附到流式事件上。仅关闭前端渲染无法阻止模型和后端继续产生这部分开销。

这次 change 需要在不破坏既有 `source-system-config` 基础设施的前提下，把“当前 source 可编辑页面”和“按 source 生效的 task progress 能力开关”设计完整。

## Goals / Non-Goals

**Goals:**

- 为当前请求 `source_id` 提供独立的 raw source config 读写接口，不暴露跨 source 选择能力。
- 在 `system-config-page` 提供当前 source 专用配置页，仅允许 `manager`/`admin` 编辑。
- 通过受代码注册的 feature switch 表单管理已知开关，同时保留未知原始配置键不被覆盖。
- 将 `feature_switches.chat_task_progress_enabled` 定义为完整能力开关，关闭后同时影响提示词、工具持久化、流式事件和前端渲染。
- 保存当前 source 配置后立即刷新前端 effective config store，确保聊天页在下一次请求即可读取到新行为。

**Non-Goals:**

- 不新增 source 选择器，不支持从当前页面跨 source 编辑其他配置。
- 不把页面做成任意 JSON 编辑器；本版仅管理受代码注册的开关，并保留未知键。
- 不在本版引入通用动态插件式配置 schema 平台。
- 不要求动态重建工具注册表；`update_task_progress` 可以继续注册，但在关闭时 no-op。
- 不把 source 系统配置写回 tenant `config.json` 或其他用户级运行时配置文件。

## Decisions

### 决策 1：新增 current-source raw config API，而不是复用 effective config 或跨 source 管理 API

新增接口：

- `GET /api/source-system-config/current`
- `PUT /api/source-system-config/current`
- `DELETE /api/source-system-config/current`

这些接口只基于当前请求上下文中的 `source_id` 工作，不接受 path `source_id` 参数，也不允许请求体覆盖目标 source。这样页面天然只能编辑当前 iframe/source 上下文。

`GET /current` 返回原始存储配置，而不是合成后的 effective config。若当前 source 没有显式记录，也返回 200：

```json
{
  "source_id": "portal",
  "config": {},
  "version": 0,
  "is_default": true,
  "updated_by": null,
  "updated_at": null
}
```

理由：

- 编辑页需要知道“当前是默认态还是显式覆盖态”，effective config 无法表达这个差异。
- 用 current-source API 可以彻底避免前端误操作其他 source。
- “无记录返回默认态对象”比 404 更适合作为表单回填语义。

备选方案：

- 直接编辑 `/effective`：无法区分默认值与覆盖值，也不适合做删除语义。
- 继续使用 `/sources/{source_id}`：前端必须持有可写 `source_id`，容易把“当前 source 页面”退化成跨 source 管理页。

### 决策 2：页面只编辑受注册字段，保存时保留未知键并裁剪默认值

页面不直接提交整份表单重建 JSON，而是采用“读取当前 raw config -> 只修改注册字段 -> 保留未知键”的写回策略。首批注册字段只包含：

```json
{
  "feature_switches": {
    "chat_task_progress_enabled": false
  }
}
```

保存语义：

- 若注册字段的新值与内置默认值相同，则从 raw config 中裁剪该显式覆盖；
- 若裁剪后整份 `config` 为空对象，则调用 `DELETE /current` 删除当前 source 记录；
- 未被页面管理的其他配置键必须原样保留。

理由：

- 避免页面覆盖掉后续其他模块写入的 source 配置。
- 显式覆盖只保留和默认值不同的内容，便于审计和长期维护。

备选方案：

- 直接覆盖整份 `config`：会丢失未知键，破坏 future-proof 能力。
- 永远保留显式值：会让“默认开启”的开关产生大量无意义存储，且不利于判断是否真的做过 source 级定制。

### 决策 3：`chat_task_progress_enabled` 是完整能力开关，不是纯前端可见性开关

当 `feature_switches.chat_task_progress_enabled=false` 时，系统需要满足以下链路级语义：

1. Agent 每轮重建系统提示词时，不再注入 task progress 相关强制要求；
2. `update_task_progress` 即使被误调用，也直接 no-op，不写入 tracker；
3. runner 在向前端透传流式事件时，不再附带 task progress 数据；
4. 前端收到事件后也不渲染步骤条区域。

默认值为 `true`，保持当前行为不变。

理由：

- 只隐藏前端 UI 并不能阻止模型继续被提示要求调用工具，也不能阻止后端继续做归一化、存储和事件附加。
- 完整关闭可以同时减少模型提示词负担、工具调用次数和无效前端状态更新。

备选方案：

- 仅关闭前端渲染：无法满足“后端不再调用模型相关步骤条逻辑”的目标。
- 动态从工具注册表移除 `update_task_progress`：实现更复杂，还需要处理运行时刷新与工具集稳定性，首版收益不高。

### 决策 4：利用现有每轮 `rebuild_sys_prompt()`，不要求工作区重建

现有 runner 每轮请求前已经会调用 `runtime.agent.rebuild_sys_prompt()`。因此只要 `_build_sys_prompt()` 在构建时读取当前 source effective config，就能让 `chat_task_progress_enabled` 在下一轮请求立即生效，无需重建 workspace、agent 实例或会话。

理由：

- 复用现有生命周期钩子，变更面最小。
- 能把配置生效粒度控制在“下一次请求”这一用户可理解的边界上。

### 决策 5：前端保存后必须主动刷新 effective config store

当前聊天页依赖 `useSourceSystemConfigStore` 中的 effective config。配置页执行 `PUT /current` 或 `DELETE /current` 成功后，必须立即调用：

```ts
useSourceSystemConfigStore.getState().loadEffectiveConfig(activeSourceId)
```

理由：

- 否则 system-config-page 已保存成功，但聊天页仍持有旧的 effective config，用户只有刷新页面或切换 source 才会看到新行为。

### 决策 6：前端补齐 `X-User-Role` 映射，并在 UI 层做访问保护

当前 source system config 管理接口要求 `X-User-Role` 为 `manager` 或 `admin`。Console 需要补齐以下映射：

- `isSuperManager === true` -> `X-User-Role: admin`
- `manager === true` -> `X-User-Role: manager`

同时页面导航与直达访问都要受权限控制：

- 非 manager/admin 不显示入口；
- 直接访问页面时渲染 403 风格状态，而不是展示可操作表单。

理由：

- 仅依赖后端 403 会让前端体验和错误提示不稳定。
- headers 映射缺失会导致页面即使对管理用户可见，也无法真正保存。

## Risks / Trade-offs

- [Risk] `update_task_progress` 仍然保留在工具集中，模型在旧上下文或异常情况下可能继续调用。
  Mitigation: 关闭时系统提示词不再要求调用，工具实现再做 no-op 兜底。

- [Risk] 页面只管理注册字段，可能让部分旧配置键长期留在 raw config 中。
  Mitigation: 保存时严格保留未知键，后续每个新开关接入时再明确自己的迁移与清理策略。

- [Risk] 当前 source 页面和跨 source 管理 API 语义并存，可能让调用方混淆。
  Mitigation: 在命名和路由层明确区分 `/current` 与 `/sources/{source_id}`，并把页面能力固定为“当前 source only”。

- [Risk] 配置在多实例之间不是绝对实时。
  Mitigation: 沿用现有 source system config 的缓存失效策略，配置页关注“下一次请求生效”，而不是跨实例瞬时一致。

## Migration Plan

1. 在后端为 source system config 增加 current-source raw config 读写删除 API。
2. 引入 feature switch 注册与默认值裁剪逻辑，首个键为 `feature_switches.chat_task_progress_enabled`。
3. 在 Console 的 `system-config-page` 增加当前 source 配置页、权限守卫、表单与保存逻辑。
4. 在请求头构建处补齐 `X-User-Role`，并在保存后刷新 effective config store。
5. 在 agent prompt、`update_task_progress`、runner 和聊天前端上接入 task progress 开关。
6. 增加聚焦测试，覆盖 raw config 默认态、保存裁剪、权限、effective 刷新和 task progress 开关行为。

Rollback：

- 前端可以移除当前 source 配置页入口并回退保存逻辑；
- 后端可停用 `/current` 接口而保留底层 source config 存储；
- `chat_task_progress_enabled` 默认值为 `true`，删除 source 显式配置即可恢复现有行为。

## Open Questions

- 后续新增更多 feature switch 时，是否需要在同一 registry 中补充展示文案、默认值、类型和归属模块元数据。
