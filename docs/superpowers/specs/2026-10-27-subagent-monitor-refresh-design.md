# SubAgent 会话监控自动刷新修复方案（已实施）

日期：2026-10-27。基线：`ab5d8ad12b65ea5464bd238e1e30e9987662929a`。方案已获用户授权，在 HEAD 95d37e060d91f6cdbd522ff64c3eadb244cf670a 工作区基线上实施，随本次修复提交。复现记录见 `analysis/playbook/subagent-monitor-refresh.md`。

## 目标与行为约定

在当前 backend chat 对应的会话内，专家触发后自动发现 Run，持续刷新至终态；暂时请求失败可恢复；旧会话异步结果不能写入当前会话。监控范围以会话为准，pending/running/paused 不因下一轮发送而消失。已完成 Run 保留到下一轮发送；下一轮仅隐藏当时已知的终态记录，仍在运行的 Run 后续完成时继续展示其终态。

## 备选方案

| 方案 | 优点 | 代价 |
|---|---|---|
| 修复现有组件的调度与请求归属（推荐） | 复用现有 GET、工具流事件、监控 UI；变更集中、可独立验证 | 运行状态仍主要以 10 秒轮询更新 |
| 当前会话始终每 10 秒轮询 | 实现简单，空列表也能发现新 Run | 无任务和全终态会话也长期请求，未解决异步归属与跨回合展示本身 |
| 后端新增专用 SubAgent SSE/订阅 | 可降低状态变化的展示延迟 | 需新增事件、重连和跨实例分发契约，超出三个问题的必要修复范围 |

本次选第一项。后端 Run 存储、触发门槛与取消协议保持当前语义。

## 一、请求失败后的恢复

- GET 失败保留最后成功 snapshot，单独记录刷新错误，不把失败解释成空 Run 列表。
- 有快照时保留状态入口；面板显示“状态刷新失败，正在重试”，恢复成功后清除。首次加载失败时展示简短重试状态，不伪造 Run。
- 使用一个会话级调度器：运行中的正常轮询每次请求结束后等待 10 秒再查；失败后也等待 10 秒再试。成功且无运行中任务时停止常规轮询。
- 同会话只允许一个状态 GET 在途；新的事件合并为一次待刷新请求，避免并发响应覆盖、请求序号持续递增造成饥饿。常规轮询和重试共用一个 timer。
- 保留工具事件立即查询、400ms 后确认的语义。确认到期时若 GET 未结束，则排队一次。事件即使密集到来也不能推迟已有查询的提交。
- start 事件后若暂时读到空结果，保留最长 30 秒的发现窗口，每 10 秒确认一次；成功发现 Run 后转为正常轮询，窗口结束仍无 Run 则停止。这避免只依赖固定 400ms 碰巧赶上落盘，也避免空列表永久轮询。
- 为该 GET 增加可选 AbortSignal，使用组件内 10 秒请求超时；超时视为刷新失败并进入上述重试，防止单个挂起请求永久阻塞调度。该参数为前端请求控制，不改变 HTTP 路径和响应结构。
- 卸载和会话切换取消 timer、AbortController。取消造成的失败不在新会话显示错误。

## 二、请求归属与异步写回

- 以当前 chatId 和生命周期 generation 标识请求归属。切换 chatId（包括 null）、卸载时使旧 generation 失效。resetKey 仅是同会话展示边界，不改变请求归属。
- GET 成功、失败、finally 的写回均检查归属；snapshot.chat_id 必须与请求 chatId 匹配。渲染时同样拒绝展示不属于当前 chatId 的 snapshot。
- cancel 的成功、失败 toast、行错误和 finally 清理都遵守同一归属检查，防止旧操作污染新会话。AbortController 仅取消本地等待，不等同于撤销已经发往后端的取消动作。
- 取消结果写入时使更早的 GET 失效，再启动确认 GET，防止旧 running 快照覆盖 cancelled。将 snapshot 与 snapshotRef 通过同一提交入口同步更新。
- 优先组件内的小型 helper/ref，避免为本次修复新增通用状态管理层或大型 polling 框架。

## 三、跨回合展示

- 保留 ChatPage 现有 resetKey，改其语义为“收起历史终态、开始新回合”。
- reset 时不清空整个 snapshot；hiddenRunIds 仅累计当时已知的 completed/partial/failed/cancelled/expired ID。pending/running/paused 保持可见。
- 不清除运行中 Run 的 stopping 状态，不允许 reset 导致同一取消请求被重复发送。
- reset 后主动安排一次刷新；保留非终态任务的后续轮询。reset 前启动的同会话 GET 可以正常提交，经新的隐藏集合过滤即可。
- 切换会话时清空隐藏集合、面板展开状态和当前会话的错误状态。重新进入旧会话时重新拉取服务端快照，沿用当前加载历史任务的行为。

## 四、恢复入口与测试基线

- `useChatRequest` 接收到有效且属于当前请求的 chat.snapshot 恢复帧后，发出一次监控刷新事件；不依赖历史数据里是否含有工具名。该分支当前提前 return，需补上刷新。旧请求恢复帧不得触发当前会话刷新。
- 流结束不是停止 SubAgent 轮询的条件；是否继续由 Run 状态、错误重试和发现窗口决定。
- `test_monitor_api.py` 使用显式构造的本地测试专家替换已移除的 plan-researcher 内置 fixture，让原始 11 项 API 测试恢复有效。不能为修测试重新加入生产内置专家。
- 工作区当前存在 `review-probe.test.tsx`，与此前复现内容一致；实施时将其用例整理并入正式测试，然后删除重复探针。实施时已将真实工具帧场景并入正式测试并删除临时探针。

## 修改范围与顺序

1. `console/src/pages/Chat/components/SubAgentRunMonitor/index.tsx`：请求归属、重试调度、reset 语义和取消写回；对应 `index.test.tsx` 先写失败回归。
2. `console/src/api/modules/chat.ts`、`chatSubagents.test.ts`：GET 的可选 signal 与传递验证。
3. `console/src/pages/Chat/components/SubAgentRunMonitor/index.module.less`：仅补已有样式体系内的刷新错误提示。
4. `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/hooks/useChatRequest.tsx` 及其测试：恢复快照后的刷新通知；工具事件辅助函数仅按必要范围调整。
5. `tests/unit/subagents/test_monitor_api.py`：替换失效 fixture，验证原 API。
6. 更新 Playbook 与本方案的实施状态。开始修改任何函数/方法前，按 AGENTS.md 对实际符号执行 GitNexus upstream impact；图谱未解析的 JSX/回调以文本和测试补验。

## 验收矩阵

| 场景 | 必须满足 |
|---|---|
| 空快照 → start 工具帧 → running → completed | 自动出现，立即/延迟查询，持续轮询，显示终态后停止 |
| 首次 GET 失败，随后恢复 | 不需要新工具事件也能重新发现 Run |
| 运行中 GET 失败，随后恢复 | 保留旧状态与入口，自动恢复并清除错误提示 |
| 请求超时/慢请求期间收到多条工具帧 | 请求可超时恢复；同会话最多一个 GET 在途；排队刷新不会丢失 |
| start 后落盘超过 400ms | 发现窗口内继续确认；无 Run 窗口到期停止 |
| A → null、A → B、A → B → A、卸载 | 旧 GET 成功/失败均不能污染当前状态 |
| cancel 请求期间切换会话 | 旧响应、错误 toast 和 finally 不影响新会话 |
| cancel 成功与旧 running GET 交错 | 不回退到旧 running，后续确认以服务器状态为准 |
| 旧 running/paused + 下一轮普通消息 | 入口与轮询继续，仍可停止 running |
| 旧 running + 新专家、新旧任务先后结束 | 两者状态独立展示，全部终态后停止轮询 |
| 历史终态 + 下一轮发送 | 历史终态隐藏；跨回合保留的任务刚完成仍显示结果状态 |
| 恢复到 chat.snapshot | 当前会话重新查询，旧会话恢复帧无副作用 |

定向检查使用现有 Vitest、RTL、pytest；Python 始终使用 `venv/bin/python -m pytest`。前端实施后执行定向测试、TypeScript、受影响文件 lint/format，再执行现有 build。ChatPage 已知 2 项上下文占用断言失败需单独报告，不以其失败掩盖本次回归，也不扩大到无关 UI 改动。真实浏览器联调需验证新会话触发、网络失败恢复、切换会话与 SSE 恢复；未执行时明确标注边界。

## 不在本次范围

后端任务跨 Pod 接管、跨实例取消、GoalMonitor 相似轮询实现、SubAgent 工具开放策略，以及全站请求错误体系的重构。上述三项已复现问题用局部前端修复及测试 fixture 修复完成。

## 实施与验收记录（2026-10-27）

- 已实现会话生命周期归属检查、单 GET 合并、请求超时、失败保留快照与重试、start 发现窗口，以及仅隐藏已知终态的 reset 语义。取消结果同步 state/ref，并失效更早 GET；旧会话取消响应不会修改行状态或触发 toast。
- 工具刷新事件携带 chatId，start 才开启发现窗口；有效 chat.snapshot 恢复后直接发出带会话归属的刷新事件，并在 await 后重新验证 owner。
- 定向前端 4 文件 70 项通过；监控 API 11 项、鉴权透传 10 项、selected_expert 9 项通过（59 项未选中）。TypeScript 与 npm run build 通过。
- 受影响文件 ESLint：除 useChatRequest.tsx 外通过；该文件保留 6 个 any 错误、2 个 Hook 依赖警告，与 HEAD 对照一致。小范围新增/修改代码的格式检查通过；按提交钩子的 79 字符行宽运行 Python Black 检查通过；工具提示 Python 3.12 与项目 3.13 目标版本差异。
- ChatPage 扩展回归 34 项通过、2 项失败，仍为既有的“上下文占用”按钮断言（794、825 行），与本次改动无关。
- Playwright 在真实浏览器加载生产 Monitor 组件和 mock API 的隔离页面，验证触发、下一轮保留、失败保持状态、恢复、停止、新建/返回会话；1440×900 和 390×844 截图检查通过。控制台仅 favicon 404，无组件运行时错误。该验证未调用真实模型或部署环境 SSE，不代表生产端到端验收。
- GitNexus detect-changes 已执行：工作区共 22 个变更文件、26 个符号、17 条受影响流程，整体标记 critical；含已有文档改动及共享聊天流/API。已人工核对本次代码 diff，修改集中于 Monitor、刷新事件、恢复分支、API signal 与测试 fixture，未修改后端运行协议。
- 临时浏览器验证页面已删除，截图保存在 output/playwright/subagent-refresh-*.png。随本次修复提交，未推送。
