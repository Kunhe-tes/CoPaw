# Plan Clarification Custom Fields Design

## Goal

让 `ask_plan_clarification` 的选择类问题默认支持用户自行填写，并确保长选项在紧凑卡片中完整可读，不改变计划澄清轮次、聊天提交方式或 Plan Mode 的阻塞语义。

## Scope

- `ask_plan_clarification` 和 `PlanClarificationCard` 默认允许自定义回复。
- 顶层单选、多选保留现有自定义文本行为。
- 表单内每个 `single_choice` 和 `multi_choice` 字段追加系统拥有的“自定义填写”选择。
- 移除表单末尾的全局“补充说明”步骤，避免与字段级自定义填写重复。
- 表单提交增加字段级自定义文本映射。
- 选项标签可换行并在限定高度的选项列表中纵向滚动。

不改变后端持久化计划模型、Plan Review 卡片、选择项的业务 ID，或普通文本字段的交互。

## Tool Contract

`allow_custom_response` 在工具输入和 `PlanClarificationCard` 中默认值改为 `true`。模型仍只负责提供实际业务选项；前端生成的“自定义填写”不是模型选项，不写进 `options`，也没有伪造的业务 ID。

工具说明和 Plan Mode 指令应说明：选择类控件天然支持用户自定义填写，调用工具时无需为“其他”生成候选项。

已有调用显式传入 `allow_custom_response=false` 时保留其语义：不显示字段级自定义选择。这样升级不会改变已有的显式禁用用例。

## Interaction

### Top-Level Choice

顶层 `single_choice` 和 `multi_choice` 继续显示自定义文本框，提交到现有 `text` 字段：

- 单选：非空文本与普通选项互斥。
- 多选：非空文本可与普通选项同时提交。

### Form Choice Fields

每个 `single_choice` 与 `multi_choice` 字段追加系统“自定义填写”行：

- 单选选择该行时展示字段内文本框，并清除标准选项选择；自定义文本非空才满足必填字段。
- 多选选择该行时展示字段内文本框；标准选项和自定义文本可以并存。若字段必填，至少选择一个标准项或填写自定义文本才满足字段。
- 文本为空的多选自定义选择不写入提交数据，也不单独满足必填字段。
- `text` 字段维持现有文本输入，不添加自定义选择行。

表单不再添加 `allow_custom_response` 驱动的全局补充说明页面。

## Submission Contract

表单澄清响应继续传递 `field_values`，并增加可选 `custom_field_values`：

```json
{
  "card_type": "plan_clarification",
  "kind": "form",
  "form_id": "planning-context",
  "field_values": {
    "scope": "backend",
    "checks": ["lint", "test"]
  },
  "custom_field_values": {
    "scope": "仅处理 CLI",
    "checks": "额外执行安全扫描"
  }
}
```

`custom_field_values` 只包含非空文本。`field_values` 保留真实选项 ID，绝不混入系统“自定义填写”标识或用户文本。面向下一轮 Agent 的 `query` 同时渲染标准选项标签和每个字段的自定义文本，保证请求上下文可读。

## Long Option Presentation

选择行保持 `min-height: 44px`，取消单行截断。标签可自然换行，长英文标识、URL 与混合中英文文本使用 `overflow-wrap: anywhere`。

选择列表保持现有最大高度 `244px` 和纵向滚动。内容超过可视区域时滚动列表而不是撑高整张卡片；完整标签通过原生 `title` 提示提供辅助读取。选项编号和选中标记保持固定尺寸，标签区域可收缩和换行。

## Compatibility And Validation

- 后端模型仍要求选择类卡片及字段包含至少一个业务选项；默认自定义能力不替代业务选项。
- 前端元数据解析兼容缺失 `allow_custom_response` 的旧卡片，将其视为默认允许自定义。
- 明确的 `allow_custom_response=false` 继续禁用自定义输入。
- 回归测试覆盖工具默认值、显式关闭、自定义单选必填、多选并存/空文本、`custom_field_values`、移除全局步骤，以及长标签的换行/滚动样式契约。

## Verification

- `venv/bin/python -m pytest tests/unit/agents/tools/test_planning.py tests/unit/app/plans/test_models.py`
- `cd console && pnpm test:run src/pages/Chat/components/PlanInteractionCards.test.tsx src/pages/Chat/messageMeta.test.ts`
- `cd console && pnpm build`

The existing Console build may need an unrelated TypeScript error fixed separately before the final build can pass; the focused test suites remain the primary regression guard for this change.
