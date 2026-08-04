# W+ 工作台 Chat 式实时运行区实现计划

## 目标与边界

将生成态中的悬浮调试预览替换为主内容区内的 Chat 式实时运行区。普通回复正文与经过脱敏的工具活动按到达顺序展示；运行结束后过程自动折叠，并在其后展示结构化问题、预跑反馈或其他工作台卡片。

本次保留现有 Session、SSE、状态机和命令提交协议。工具活动只暴露工具名称、服务标签和运行状态，不暴露参数、原始输出、思考内容或上游任意结构化数据。顶部环节导航保留，只移除生成卡片内部的估算进度条。

## 实现单元

### U1. 扩展安全实时流投影

**目标：** 在现有 `safe_stream_trace` 中追加有序、安全的正文与工具活动条目。

**文件：**

- `src/swe/app/wplus_sop/runtime.py`
- `src/swe/app/wplus_sop/router.py`
- `tests/unit/app/wplus_sop/test_runtime.py`
- `tests/unit/app/wplus_sop/test_router.py`

**方案：** 沿用有界、进程内、按 run 隔离的安全缓冲；完成后的快照冻结到同一 Session 开始下一轮或被全局容量淘汰，以便前端收到最后一帧并折叠审计。保留 `summary_text` 兼容字段，新增条目列表。工具帧仅解析允许展示的名称、服务标签和状态，不复制参数、输出或摘要正文。

**测试场景：**

1. 普通 assistant 文本与工具调用按照到达顺序形成条目。
2. 工具完成和失败会更新同一条工具活动的状态。
3. 参数、工具输出、reasoning 和未知数据均不会进入投影。
4. SSE 事件包含新条目且仍不写入持久化事件日志。

### U2. 实现主内容区实时运行组件

**依赖：** U1

**文件：**

- `console/src/api/types/wplusSop.ts`
- `console/src/pages/WPlusSopWorkspace/index.tsx`
- `console/src/pages/WPlusSopWorkspace/index.module.less`
- `console/src/pages/WPlusSopWorkspace/index.test.tsx`

**方案：** 用内嵌消息流替代 Popover。生成时保持展开并自动跟随最新内容；状态离开生成态后自动折叠，允许用户再次展开审计。结构化主面板始终位于运行区之后。移除生成卡片内部 Progress，保留总体环节导航。

**测试场景：**

1. 生成中正文和工具活动直接可见且没有调试悬浮按钮和内部进度条。
2. 新条目到达时按序追加，旧序号和旧 run 仍被忽略。
3. 进入 `AwaitingAnswer` 后运行区自动折叠，问题卡片紧随其后展示。
4. 折叠控件支持键盘操作、状态文案和失败状态，不依赖颜色表达。

## 验证

- 后端 W+ runtime/router 定向测试。
- 工作台 Vitest 定向测试。
- 前端 ESLint、Prettier 和测试构建。
- `git diff --check` 与 GitNexus `detect_changes()`。
