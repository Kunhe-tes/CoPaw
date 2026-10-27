# SubAgent 会话展示与自动刷新检查

核对日期：2026-10-27。源码基线：`ab5d8ad12b65ea5464bd238e1e30e9987662929a`，工作区现有文档改动保留。GitNexus 绑定 `/Users/shixiangyi/code/Swe`（CoPaw），索引 commit 与 HEAD 一致。图谱未解析 JSX 对监控组件的调用边，相关关系以源码为准。

## 结论与正常链路

原实现存在请求失败后停轮询、切换空会话接收旧响应、下一轮隐藏运行中任务三项缺陷。2026-10-27 已实施修复；下文保留原始复现，最新实现与验收见“修复落地”。

1. `console/src/pages/Chat/index.tsx` 提交 `selected_expert_id`，本轮提交后清空专家选择并增加 `subAgentMonitorResetKey`。
2. `runner.py::_selected_expert_start_tool_call` 将管理 UUID 解析为启用专家的运行名称，生成强制 `start_subagent`；Tool Guard 接受启动后继续发出 wait/get，直到选定 Run 终态。Plan/Goal 请求不会走普通专家选择路径。
3. `runner/utils.py` 将工具调用/结果转换为包含 `content[].data.name` 的流帧；`useChatRequest.tsx:565` 将帧交给 `emitSubAgentRunsRefreshIfPresent`。
4. 事件识别 start/wait/get/cancel 四种工具名。Monitor 收到事件立即 GET，再于 400ms 后确认一次；发现非终态可见 Run 后每 10 秒 GET，全部终态停止轮询。这里不是后台 worker 主动推送状态。
5. `/subagents/runs?chat_id=...` 先解析 backend chat，再按 `chat.session_id` 过滤持久化 Run。Monitor 使用 `feedbackChatId`，不是直接使用逻辑 session_id。

## 原始问题与复现

### P1：一次快照请求失败会切断后续轮询

位置：`console/src/pages/Chat/components/SubAgentRunMonitor/index.tsx:106-110,144-150`。

- `refresh` 的 catch 清空 snapshot；可见 Run 随即为空，轮询 effect 清理 interval。
- 复现：先返回 running，10 秒后的 GET reject，再推进 30 秒，请求数仍为 2，入口消失。
- 后续工具流事件或重新进入会话可以重新触发 GET；若 SSE 已结束/断开或没有新工具帧，则网络恢复也不会自行重试。初次 GET 失败也没有独立重试。
- 建议：保留最后成功快照并显示刷新失败；独立维护重试/轮询条件，不让暂时的网络错误被解释为没有 Run。验收需覆盖初次失败、运行中失败和随后恢复。

### P2：切到无 chatId 的新会话后，旧请求仍可写入

位置：同文件 `:93-99,114-122`。

- A 会话发起 GET 后切换到 `chatId=null`；新 refresh 在增加 requestSeq 前 return，旧请求没有被失效。effect cleanup 也没有失效请求。
- 复现：A 的延迟请求随后 resolve，空白新会话出现 A 的“助手运行状态”入口。此时控件绑定的 chatId 已为空，停止动作也无法执行。
- 非空 A → 非空 B 通常由 B 的新序号阻止旧响应；此次确认的是 A → null 边界。
- 建议：chatId 变化及卸载时失效在途请求，并在提交响应时校验请求所属会话。验收覆盖 A → null、A → B、卸载以及旧取消请求晚返回。

### P2：下一轮提交会隐藏仍在运行的历史 Run 并停轮询

位置：`console/src/pages/Chat/index.tsx:2179`，Monitor `:124-145`。

- reset 无条件把已知 Run ID 全部写入 hiddenRunIds，包含 pending/running/paused，清空 snapshot 且不重新 GET。
- 复现：已加载 running Run，resetKey 从 0 改为 1，再推进 30 秒，请求数仍为 1，入口隐藏。即使下一轮出现新专家事件，该旧 ID 在本次挂载期间仍被过滤。
- 当上一轮中断/提前结束但后台 Run 仍存活，随后用户发送普通消息时，会失去观察和停止入口。
- 当前测试明确覆盖“清空此前 Run”，所以这是现有回合展示语义与“会话内持续监控”要求的冲突，不能只补一条强制 refresh 就解决。
- 建议：确认持续监控以 session 为范围后，仅隐藏已终态历史 Run，保留非终态 Run 的展示与轮询；验收覆盖旧 running + 新回合无专家、旧 running + 新专家、旧 Run 随后终态。

## 修复前验证记录

- 原有前端：SubAgentRunMonitor、chatSubagents API、useChatRequest 共 39 项通过。
- 扩大到 ChatPage 后：4 个测试文件共 71 项通过、2 项失败。失败均为 `Chat/index.test.tsx` 查找“上下文占用”按钮的原有断言（第 794、825 行附近），与本次 SubAgent 探针分开记录；该范围不能报告全绿。
- 临时 RTL/Vitest 探针：模拟真实 `plugin_call_output/content/data/name=start_subagent` 帧，空列表 → 立即发现 Run → 400ms 确认 → 10 秒轮询 → completed 停止，1 项通过；三个问题各有 1 项失败探针，均按预期复现。探针运行后删除，避免将失败测试留在项目测试集中。
- `test_runner_auth_token_passthrough.py`：10 项通过。
- `test_react_agent_and_guard_integration.py -k selected_expert`：9 项通过、52 项未选中。
- 原始 `test_monitor_api.py`：1 项通过、10 项失败，均在 fixture 解析已移除的 `plan-researcher` 内置定义时抛 KeyError，未执行到 HTTP 断言。
- 仅在测试进程的 collection 阶段替换该 fixture provider 为明确构造的测试定义，生产文件不变，同文件 11 项通过；这只验证监控路由本身，不代表原始测试基线已修复。
- 未启动真实模型会话或浏览器端到端环境；不把组件/API 测试通过视为完整线上验收。

常用命令：

```bash
cd console
./node_modules/.bin/vitest run src/pages/Chat/components/SubAgentRunMonitor/index.test.tsx src/api/modules/chatSubagents.test.ts src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/hooks/useChatRequest.test.tsx
```

```bash
venv/bin/python -m pytest tests/unit/app/test_runner_auth_token_passthrough.py -q
venv/bin/python -m pytest tests/unit/subagents/test_react_agent_and_guard_integration.py -k selected_expert -q
venv/bin/python -m pytest tests/unit/subagents/test_monitor_api.py -q
```

## 修复落地

当前实现以 chatId 和组件生命周期 token 校验 GET/cancel 写回，同会话 reset 不失效 GET。GET 使用 10 秒超时、请求结束后 10 秒调度；错误保留最后快照并独立重试。start 事件有 400ms 确认与最长 30 秒发现窗口，wait/get/cancel 不开启新发现窗口。事件携带 chatId；chat.snapshot 恢复由控制器在成功应用历史、重新检查 owner 后，释放 owner 之前通知 Monitor。

恢复回调正常完成也会清空 activeRequestOwner，因此不能在 await applyRecoverySnapshot 返回后用 owner 是否仍活跃判断是否刷新。请求层先将已校验的 snapshot.chat_id 写入 owner，控制器在成功分支发出一次 discover=true；异步刷新期间切换会话则不发事件。回归测试须调用真实恢复回调，覆盖直接应用快照、兼容 refreshSession、事件先于 owner 释放，以及异步刷新期间 owner 被替换。

该生命周期修正先以真实控制器回调复现两项零事件失败，再验证通过。2026-10-27 聚焦前端六个测试文件共 82 项、Python monitor API 11 项、TypeScript、受影响文件 Prettier 和生产构建通过。两个生产 Hook 的 ESLint 诊断与 HEAD 相同（忽略行号移动），仍有既有 6 个错误和 5 个警告；构建仍有分包与体积警告。

下一轮仅累计隐藏当时已知终态 ID，pending/running/paused 保留展示与轮询。取消请求跨 reset 保持停止中并防重入，成功后使旧 GET 失效，再以取消结果更新 state/ref 和查询确认。

排查时依次检查：
1. stream 工具帧是否包含 start_subagent/wait_subagent/get_subagent/cancel_subagent，刷新事件 chatId 是否等于 Monitor 的 backend chatId。
2. snapshot.chat_id 是否匹配请求；失败时应保留快照，10 秒后重试；单个 GET 10 秒后应 abort。
3. resetKey 是否仅表示同会话新一轮；不能将运行中 ID 加入隐藏集合。
4. 旧 GET/cancel/recovery owner 是否已在会话切换、卸载或取消结果提交时失效。

### 修复后验收

- 前端 Monitor/API/request/useChatRequest：70 项通过，覆盖真实嵌套工具帧、失败/超时恢复、请求合并、发现窗口、A→null/B/A、卸载/StrictMode、取消交错、跨回合多任务与恢复 owner。
- Python monitor API：11 项通过；显式 SubAgentDefinition 测试 fixture 代替已移除的内置专家。auth token passthrough：10 项通过；selected_expert：9 项通过、59 项未选中。
- TypeScript、生产构建、git diff --check 通过；构建有已有体积警告。useChatRequest 的 6 个 ESLint 错误和 2 个警告与 HEAD 一致；其他本次受影响 TS 文件 lint 通过。按提交钩子的 79 字符行宽运行 Python Black 检查通过。
- ChatPage 独立扩展测试 34 通过、2 失败，仍是“上下文占用”原断言，未修改无关 UI。
- Playwright 以真实生产组件/mock API 验证触发→展示、reset 保留、失败提示与恢复、取消、新建/返回会话；桌面和窄屏截图通过。未做真实模型、跨 Pod 或生产 SSE 联调。
- GitNexus 最终检测整体 critical（共享 API/聊天流及既有工作区改动），已逐项核对代码范围；随本次修复提交，未推送。
