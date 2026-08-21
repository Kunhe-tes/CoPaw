# W+ 工作台流式调试预览实现计划

## 目标

在 W+ SOP 工作台处于生成态时，提供一个可悬停、可聚焦、可点击的“实时流追踪”调试入口，展示当前 Agent 流的安全追踪摘要，帮助定位“正在生成”卡住的问题。

## 边界

- 预览只包含固定白名单的帧类型、状态、序号和内容长度，不包含任何正文。
- assistant/reasoning 正文、工具调用/输出、MCP/函数参数、附件、任意上游标签、运行元数据和原始客户数据均不进入缓冲。
- 预览仅保存在当前 Agent 进程内，不写入 W+ Session、事件存储、Chat 投影或审计记录。
- 调试帧不推进 `state_version`，前端不得把它交给 `applySessionEvent`。
- 追踪按运行隔离，内部缓冲本身固定容量；新运行开始时清空同 Session 旧预览，运行结束时删除。
- SSE 断线重连后可以重新取得当前进程内的最新预览；进程重启后为空是预期行为。

## 交互

- 生成面板增加次要的“实时流追踪（调试）”按钮。
- 鼠标悬停、键盘聚焦或点击均可打开浮层，避免 hover-only。
- 浮层使用等宽文本、保留换行、限制宽高并允许内部滚动；打开时定位到最新记录，用户主动上滚后暂停自动跟随。
- 尚无安全文本时展示明确空状态。
- 浮层注明“仅展示帧类型、状态和长度；文本正文、工具输出和结构化业务数据均已隐藏”。

## 实现切片

### 1. 后台安全预览缓冲

修改：

- `src/swe/app/wplus_sop/runtime.py`
- `tests/unit/app/wplus_sop/test_runtime.py`

先写测试覆盖：

- 敏感正文和工具内容永远不会进入预览。
- reasoning、工具、函数、MCP 和未知帧只产生固定白名单摘要。
- 按 `sop_session_id + run_id` 隔离，同时限制最大字符数、最大行数和活动运行数。
- 正常完成、异常和取消后都清理运行缓冲。

实现一个 W+ 专用的进程内追踪注册表，在现有内部订阅者消费 Agent SSE 时同步写入不含正文的安全摘要。

### 2. W+ SSE 调试帧

修改：

- `src/swe/app/wplus_sop/router.py`
- `tests/unit/app/wplus_sop/test_router.py`

先写测试覆盖：

- 仅向通过现有 ownership 校验的 Session 返回预览。
- 追踪摘要变化时发送 `safe_stream_trace`，字段使用 `summary_text` 明确表达其不含原始正文。
- 调试帧沿用当前 Session `state_version`，但不写入持久事件。
- 内容不变时不重复发送。

### 3. 工作台浮层

修改：

- `console/src/api/types/wplusSop.ts`
- `console/src/pages/WPlusSopWorkspace/index.tsx`
- `console/src/pages/WPlusSopWorkspace/index.module.less`
- `console/src/pages/WPlusSopWorkspace/index.test.tsx`

先写测试覆盖：

- 调试帧只更新本地预览，不触发 Session 版本应用或重载。
- 生成态显示入口；悬停/聚焦/点击可查看内容。
- 空追踪、截断提示、自动跟随尾部和长文本滚动容器完整。
- 切换到新 `run_id` 或退出生成态时不会把旧运行内容误显示为当前输出。

## 验证

- 后台 W+ runtime/router 定向 pytest。
- 工作台和 W+ API 定向 Vitest。
- Console TypeScript 检查和受影响前端测试。
- 浏览器验证桌面与窄屏的 hover、focus、click、长文本和空状态。
- 独立检查正确性、安全/隐私、可访问性/响应式、可维护性。
- 最后运行 GitNexus `detect-changes`，确认影响范围只落在 W+ 运行时、SSE 和工作台。
