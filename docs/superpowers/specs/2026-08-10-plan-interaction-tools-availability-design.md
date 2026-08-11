# 计划交互工具开放设计

## 目标

默认仅在 Plan Mode 向 Main Agent 注册 `ask_plan_clarification` 与
`submit_proposed_plan`。Source 管理员可在系统特性配置中通过“计划交互工具开放”
允许普通模式也注册这两个工具。

## 范围

- 新增 Source 级布尔开关
  `feature_switches.normal_mode_plan_interaction_tools_enabled`，默认 `false`。
- 系统特性配置页面在“对话与执行”中显示“计划交互工具开放”开关。
- Main Agent 的注册条件为：Plan Mode 已开启，或该 Source 的开关已开启。
- 两个工具作为一个能力同时注册或移除。

## 不在范围内

- 不为普通模式追加 Plan Mode 的系统提示词或权限限制。
- 不向 SubAgent 注册计划交互工具。
- 不拆分两个工具的开关，也不修改现有计划卡片、审核存储或前端交互。

## 运行时行为

| 场景 | 工具目录 | 提示词与模式 |
| --- | --- | --- |
| Plan Mode，任意开关值 | 两个工具均可用 | 保持现有 Plan Mode 指令和只读策略 |
| 普通模式，开关关闭 | 两个工具均不可用 | 保持普通模式 |
| 普通模式，开关开启 | 两个工具均可用 | 不注入 Plan Mode 指令，不改变权限 |
| SubAgent，任意模式或开关值 | 两个工具均不可用 | 保持现有 SubAgent 策略 |

配置更新在当前 Source 的后续 Agent 请求中生效。已经开始的 Agent 回合继续使用
其创建时的工具目录。

普通模式提交的计划仍走现有审核路径：`revise` 进入或保持 Plan Mode，`execute`
接受计划并在正常模式执行，`exit_plan` 关闭 Plan Mode。

## 实现边界

- 后端在 Source 系统配置注册表中定义开关、默认值和读取 helper。
- `SWEAgent._create_toolkit` 用该 helper 决定普通模式是否加入成对工具；Plan Mode
  的白名单和注册结果不依赖开关。
- Console 复用现有 Source 配置开关注册和工作台路径追踪机制，保证读取、编辑、保存、
  重置和未保存状态一致。

## 验证

- Source 配置默认值、合并、校验和 helper 测试。
- Main Agent 的四种模式/开关组合，以及 SubAgent 排除测试。
- 系统提示词测试，确认普通模式开关不会注入 Plan Mode 指令。
- Console 注册表、工作台摘要和保存载荷测试。
