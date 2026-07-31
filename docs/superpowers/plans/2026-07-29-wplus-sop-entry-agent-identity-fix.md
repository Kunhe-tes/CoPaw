# W+ SOP 入口 Agent 身份修复计划

## 目标

修复 Console 通过非 Agent-scoped 路径发起 W+ SOP 请求时，入口因
`request.state.agent_id` 为空而返回
`W+ SOP entry requires tenant/source/user/agent` 的问题。

## 边界

- 只修改 W+ 入口对可信 Agent 身份的解析。
- 继续以中间件身份和后端已经解析出的 Workspace 为可信来源。
- 不从用户 payload、`selected_skill_names` 或自由文本接收 Agent 身份。
- 不修改 W+ Session、状态机、SSE 或 Skill 协议。
- 不修改 ADR；这是既有身份边界内的缺陷修复。

## 实施步骤

1. 在 `tests/unit/routers/test_console_wplus_sop_entry.py` 增加回归场景：
   请求状态具有 tenant/source/user，但没有 `agent_id`；后端已解析出的
   Workspace 具有 `agent_id`。显式选择 `wplus-sop-miner` 时必须返回入口卡。
2. 先运行该测试，确认当前实现以 HTTP 400 失败。
3. 在 `src/swe/app/routers/console.py::post_console_chat` 中使用
   `request.state.agent_id`，缺失时回退到已经验证的
   `workspace.agent_id`。
4. 保留现有 Agent 不一致校验，确保显式的请求状态 Agent 与 Workspace
   Agent 不一致时仍返回 HTTP 403。
5. 运行：

   ```powershell
   & .\.venv\Scripts\python.exe -m pytest tests/unit/routers/test_console_wplus_sop_entry.py -q
   & .\.venv\Scripts\python.exe -m pytest tests/unit/app/wplus_sop tests/unit/routers/test_console_wplus_sop_entry.py -q
   ```

6. 运行独立代码审查，修复 Critical/Important 问题后重新验证。
7. 运行 `git diff --check` 和 GitNexus `detect_changes`，确认变更范围。

## 验收标准

- 缺少 `request.state.agent_id` 但 Workspace 已确定 Agent 时，W+ 入口成功。
- tenant/source/user 任一缺失时仍失败关闭。
- 请求状态 Agent 与 Workspace Agent 不一致时仍返回 HTTP 403。
- 重复请求、已有 Session 和普通 Chat 流程行为不变。
