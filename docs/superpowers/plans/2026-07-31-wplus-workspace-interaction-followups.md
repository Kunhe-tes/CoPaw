# W+ SOP 工作台交互补全计划

日期：2026-07-31  
状态：进行中

## 目标

在不改变既有路由、权限、所属 Chat 和事件状态机语义的前提下，补全五项交互：

1. 用户可见文案不出现产品宿主名称。
2. Agent 首次候选环节仍限制为 2–4 个；用户手工确认的队列只限制至少 2 个，不设上限。
3. 保存并退出后返回所属 Chat，并持续展示可重新进入工作台的入口。
4. 标记为需要自定义输入的单选或多选选项，在选中后显示文本输入框，回答同时保留选项 ID 和自定义文本。
5. 实时流追踪只展示普通 assistant message 的文本内容，不展示 reasoning、工具调用、工具输出或格式化渲染。

## 契约决定

- `StageProposalPayload` 单独执行 2–4 个候选环节校验；`StageQueueConfirmedPayload` 与持久化 `StageQueue` 只要求至少 2 个。
- 问题选项增加向后兼容字段 `requires_custom_input: boolean = false`。
- 自定义回答使用 `{ selected_option_ids: string[], text: string }`；后端继续接受旧的 `string` 与 `string[]`。
- 暂停态仍持有所属 Chat 的活动会话槽；Chat 入口直接读取 active-session，不依赖刚返回时的消息元数据刷新。
- 流追踪继续保持有界、进程内、运行结束即清理；只收集 `role=assistant` 且 `type=message` 的 text content。

## 实现单元

### 1. 前端交互

- 修改 `console/src/pages/WPlusSopWorkspace/index.tsx`、`sessionView.ts`、`index.module.less` 与 API 类型。
- 修改 `console/src/pages/Chat/index.tsx`，挂载现有活动工作台条并按活动态锁定 Chat 输入。
- 修改 `WPlusSopActiveBar` 用户文案和测试。
- 先补失败测试：第 5 个环节可新增/确认、自定义选项输入与提交、保存退出导航、暂停态恢复入口。

### 2. 后端协议

- 修改 `models.py` 拆分候选队列与确认队列上限。
- 修改 `service.py` 解析新旧两种回答值，并校验被选中的自定义选项必须提供文本。
- 补模型与服务测试，覆盖 5 个确认环节、5 个候选被拒绝、单选/多选自定义回答及旧协议兼容。

### 3. 实时文本追踪

- 修改 `runtime.py`，按 Chat 响应构建器的 message/content 语义收集普通 assistant 文本。
- 忽略 reasoning、MCP/function/plugin/component 调用、tool output 与非文本内容。
- 保留字符数、活动运行数和生命周期清理上限；补增量、完成帧替换、工具隔离和截断测试。

### 4. 文档与验证

- 更新 ADR 0013，记录候选与人工队列的不同上限、自定义选项协议、Chat 恢复入口和流追踪边界。
- 运行 W+ 后端单测、工作台/入口前端单测、lint/type/build。
- 在 1280×720、1440×900、1920×1080 与 `hideMenu=true` 下检查入口、输入框、弹层和无水平溢出。

## 验收标准

- 页面与入口相关用户可见文案中不包含宿主产品名。
- 4 个候选后仍可手动新增到 5 个及以上并成功提交；Agent 直接提交 5 个候选仍被拒绝。
- 点击保存并退出会回到准确的所属 Chat；刷新或重新聚焦后仍可见“继续工作”入口。
- 选择自定义选项后立即出现输入框，取消选择后输入框消失；必填自定义文本为空时不能提交。
- 调试悬浮层能看到与 Chat 普通回复相同的文本增量，且看不到工具参数、工具输出或 reasoning 文本。
