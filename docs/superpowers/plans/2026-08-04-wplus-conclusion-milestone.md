# W+ SOP 固定结论里程碑计划

## 问题与边界

工作区进度条只渲染 `session.stages` 中由用户确认的业务环节。当业务队列少于四项时，四列布局会留下空位，也无法显式表达 ADR-0013 已定义的 `FinalizingOutputs → MemoryReview → Completed` 最终路径。

本改动只在前端进度投影中追加固定、只读的“生成结论”里程碑。它不写入 `session.stages`，不参与队列编辑、提问、预跑或环节确认，也不改变现有百分比计算。

## 决策

- 业务环节之后始终追加一个固定的“生成结论”里程碑。
- `FinalizingOutputs` 和 `MemoryReview` 将该里程碑显示为当前；`Completed` 显示为已完成；此前状态显示为等待中。
- 终止、暂停和可恢复失败不伪造结论已经开始或完成，继续依赖已持久化的业务环节状态。
- 保留现有最多 94% 的业务进度上限，最终完成后才显示 100%。

## 实施单元

### U1. 用测试固定结论里程碑投影

**文件：**

- `console/src/pages/WPlusSopWorkspace/index.test.tsx`

**执行说明：** 先增加失败测试，再实现行为。

**测试场景：**

- 普通业务处理中，结论里程碑排在所有业务环节之后并显示“等待中”。
- `FinalizingOutputs` 与 `MemoryReview` 显示结论为当前状态。
- `Completed` 显示结论已完成，并保持总体进度 100%。

### U2. 实现只读终点投影

**依赖：** U1

**文件：**

- `console/src/pages/WPlusSopWorkspace/index.tsx`

**实现方式：** 复用现有进度项 DOM 和 `data-status` 样式，在渲染层根据 Session 状态推导结论里程碑，不修改 API 类型或后端持久化模型。

## 验证

- W+ 工作区聚焦测试通过。
- Console TypeScript 检查通过。
- 真实浏览器验证三项和四项业务队列均能在末尾看到结论里程碑。
- GitNexus 变更检测与 `git diff --check` 仅报告预期前端范围。
