# Expert-as-main 浏览器验证报告

日期：2026-10-27（Asia/Shanghai）。工作树：/Users/shixiangyi/code/Swe/.worktrees/expert-as-main。

## 结论与边界

真实 Chromium + 本机 Console + 完全本地 mock API 已验证：选择即保存、完整刷新恢复、HTTP 409 身份同步、修复后可见 Welcome 草稿和附件恢复、编辑后重发，以及 Plan/Goal 退出提示。首轮 409 曾实际暴露 P1：草稿仅恢复到隐藏普通输入框；前端修复后重新执行并通过可见输入框、附件芯片、再次发送 payload 三层检查。

结论只覆盖浏览器 UI 与 HTTP 请求构造/响应处理，不是完整功能验收，也不代表真实后端、模型或部署环境端到端通过。

## 环境与隔离

- Playwright CLI 会话 expert-main-smoke：先打开空白页，再安装拦截，之后进入应用。采用 /Users/shixiangyi/.codex/skills/playwright/SKILL.md 的 CLI 工作流。
- Vite v6.4.2，本机地址 http://127.0.0.1:5177/；在 console/ 执行 npm run dev -- --host 127.0.0.1 --port 5177 --strictPort。
- 所有 /api/* 由 Playwright route 本地返回；其他 origin 的请求中止；env-grey-control.js 替换为空本地配置。未使用真实用户凭据，浏览器 API 未转发给 Vite 后端代理。
- 合成 Chat：00000000-0000-0000-0000-000000000701；用户/会话：browser-smoke-user / browser-smoke；专家：expert-a、expert-b。
- 模型配置为合成 browser-mock-model，未实际调用模型。临时 browser-smoke.txt 为 31 B，上传响应亦是本地 mock，没有真实后端上传。
- 只读检查 lsof -nP -iTCP:8088 -sTCP:LISTEN 未找到本机 8088 listener。未启动真实后端或执行登录。

## 实际操作与结果

| 检查 | 操作及证据 | 结果 |
| --- | --- | --- |
| 选择即保存 | 空白 Chat 快捷操作 → 专家 → 浏览器专家 A；尚未发消息已有请求 1513 POST chats、1514 GET binding、1515 PUT binding，URL 转为持久 Chat ID | 通过，mock 范围 |
| 完整刷新恢复 | 页面 reload 后重新读取绑定，Welcome 按钮显示 A；补齐模型 fixture 后再次完整 reload 仍显示 A | 通过，mock 状态跨 reload 保留 |
| 文件上传 | 浏览器文件选择器选 31 B 临时文件；请求 6141 POST upload 200，发送前芯片显示 browser-smoke.txt / 31 B | 通过，mock upload |
| 409 身份同步 | 请求 6148 POST console/chat 409，响应 revision 2 / expert-b，可见专家按钮同步 B | 通过 |
| 409 草稿/附件，修复前 | Toast 声称保留，但可见 Welcome 空；原文本与附件仅在隐藏普通输入框 | 首次失败，P1 上报并由前端修复 |
| 409 草稿/附件，修复后 | 重置 A/revision 1，从 UI 重新上传、输入、发送；请求 8117 409 后，可见 Welcome 文本、31 B 芯片均恢复，身份 B | 复测通过 |
| 恢复后编辑稳定性 | 编辑为 409 browser smoke draft — edited after recovery，打开/关闭快捷菜单后文本和附件仍在 | 通过 |
| 重发完整性 | 请求 8131 保留编辑后文本、相同文件路径/大小、最新 revision 2；再次 mock 409 到 revision 3 后，可见文本与芯片仍在 | 通过 |
| Plan 退出提示 | A 绑定下切换计划；请求 9675 更新 meta、9676 GET binding；计划按钮可见、专家按钮消失，显示默认 Agent 通知 | 通过，mock 模拟后端解除绑定 |
| Goal 退出提示 | 重置 A 后切换目标；请求 11196 更新 meta、11197 GET binding；目标按钮可见、专家按钮消失，显示相同通知 | 通过，mock 模拟后端解除绑定 |
| 开关关闭时 legacy | source switch=false，选择 A 后发 harmless draft；请求 12719 带 selected_expert_id=expert-a，选择期间无 binding PUT | 已观察 legacy 选择/构造路径，未验证真实执行 |
| 回答专家身份 | 未建立可信完整回答流 fixture，409 路径没有成功模型回答 | 未做浏览器验证 |

Plan/Goal 实际通知：已解除会话专家绑定，当前模式使用默认 Agent。观察到的是切换后的通知，不是发送前确认对话框；未执行 Plan/Goal 任务。

## 核心请求证据

请求 1515 在发送消息之前，body 为：

~~~json
{"expected_revision":0,"expert_id":"expert-a"}
~~~

请求 6148（修复前 P1）的关键字段：

~~~json
{
  "input":[{"role":"user","type":"message","content":[
    {"type":"text","text":"409 browser smoke draft — keep text and attachment","status":"created"},
    {"type":"file","file_url":"/browser-smoke.txt","file_name":"browser-smoke.txt","file_size":31,"status":"created"}
  ]}],
  "session_id":"browser-smoke",
  "expert_binding_revision":1,
  "chat_id":"00000000-0000-0000-0000-000000000701"
}
~~~

其 mock HTTP 409 响应：

~~~json
{"detail":{"code":"expert_binding_changed","expert_binding":{"revision":2,"expert_id":"expert-b","enabled":true,"available":true,"expert_name":"浏览器专家 B","reason":null}}}
~~~

修复前只读 DOM：可见 Welcome editor 为 652×30，text 为空；含原文本的普通 editor 为 0×0；browser-smoke.txt 节点也是 0×0，因此没有将 toast 当作保留成功证据。

修复后请求 8117 409：可见 Welcome editor 为 652×30，text 为原草稿；可见附件节点 browser-smoke.txt 为 82×22。被动事件观察显示 restore event 触发时仅有普通 editor，覆盖恢复跨 Welcome 重新挂载的实际场景。

请求 8131（编辑并重发）的关键字段：

~~~json
{
  "input":[{"role":"user","type":"message","content":[
    {"type":"text","text":"409 browser smoke draft — edited after recovery","status":"created"},
    {"type":"file","file_url":"/browser-smoke.txt","file_name":"browser-smoke.txt","file_size":31,"status":"created"}
  ]}],
  "mode":"normal",
  "goal_mode_enabled":false,
  "expert_binding_revision":2,
  "chat_id":"00000000-0000-0000-0000-000000000701"
}
~~~

Plan 请求 9675：{"meta":{"plan_mode_enabled":true}}。

Goal 请求 11196：{"meta":{"goal_mode_enabled":true,"plan_mode_enabled":false}}。

开关关闭请求 12719 同时出现 selected_expert_id=expert-a 与 expert_binding_revision=20；仅确认观察到的字段，不称为真实 legacy 后端通过。该请求由 mock 刻意返回 400 以终止执行。

## 实际证据路径

以下路径均实际产生，属于本机临时/忽略目录，不是随报告提交的可移植附件：

- 修复前截图：/tmp/expert-main-browser/first-turn-conflict.png。
- 修复前快照：.playwright-cli/page-2026-10-27T04-00-53-586Z.yml。
- 修复后首次恢复：.playwright-cli/page-2026-10-27T04-43-02-194Z.yml。
- 修复后重发：.playwright-cli/page-2026-10-27T04-43-40-778Z.yml。
- Plan：.playwright-cli/page-2026-10-27T04-46-24-359Z.yml。
- Goal：.playwright-cli/page-2026-10-27T04-47-12-273Z.yml。
- legacy：.playwright-cli/page-2026-10-27T04-48-07-280Z.yml。
- Console 日志：.playwright-cli/console-2026-10-27T03-51-00-503Z.log。
- mock 脚本：/tmp/expert-main-browser/setup.cjs、model-fixture.cjs、conflict-retest.cjs、mode-fixture.cjs、legacy-fixture.cjs。

包装脚本：/Users/shixiangyi/.codex/skills/playwright/scripts/playwright_cli.sh。实际使用的核心命令为 --session expert-main-smoke snapshot/click/fill/upload/requests，以及 request-body 1515、request-body 6148、response-body 6148、request-body 8131、response-body 8131。只读 eval 记录 contenteditable 文本和 boundingClientRect，避免仅凭提示文案断言。

## 限制及执行中修正

- 初始 goals 辅助 mock 形状不符曾导致 GoalMonitor 报错；修正为 JSON null 后恢复。首次发送也因 active model fixture 缺失被客户端以 Model not configured 阻止，未产生 console/chat；补齐合成配置后才完成 HTTP 409。二者为 fixture 修正，不记为产品缺陷。
- 第一版模式 mock 没模拟 Plan/Goal 开启时后端解除绑定，造成旧专家仍显示；补齐合同后重新执行上述检查，没有将不完整 fixture 的结果算成功。
- Console 日志仍有 React flushSync、样式 :first-child、表单提示和辅助 mock 404/任务列表不可用信息。不声称 Console 零错误或所有页面通过。
- 未验证真实登录、真实模型回答、回答历史身份浏览器展示、LLM/MCP/Skill 实际调用、stop/cancel、审批、真实文件存储、真实绑定 CAS/跨进程竞争、数据库/Redis、跨 Kubernetes、NAS、真实租户隔离。其他报告的单测/后端证据不能由这次 mock 浏览器结果替代。
- 本次浏览器执行者只新增本报告；P1 生产修复由前端执行者完成，主执行者负责集成和提交。

## 清理

本次 Playwright expert-main-smoke 会话已关闭（CLI 返回 Browser closed），Vite :5177 已通过其专属 session 中断退出（exit 130），复查 5177 无 listener。临时 mock 与截图保留于 /tmp/expert-main-browser/ 供追溯，不要求主执行者维护浏览器或开发服务器。
