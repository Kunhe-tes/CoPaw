# W+ SOP 仅显式技能入口实施计划

> 2026-08-04 更新：正文中的独立、精确 `@wplus-sop-miner` 已被确认为第二种显式入口。
> 当前契约与实施计划见 `2026-08-04-wplus-explicit-mention-entry.md`；本文保留为决策历史。

## 问题与边界

当前 W+ SOP 新入口同时接受受信任的技能选择和普通文本的隐式语义识别。现在收紧为：只有请求中的结构化 `selected_skill_names` 明确包含 `wplus-sop-miner` 时，才返回进入工作台的确认卡。

仅在消息正文中手打技能名不构成授权。普通文本继续进入普通 Chat。已有活动或暂停 Session 的返回/恢复入口、历史 implicit 提议的拒绝回放与持久化兼容不变。

## 决策

- 保留进入确认卡；显式选择不会自动创建 Session 或自动跳转。
- `classify_wplus_entry` 不再加载有效技能目录或运行 `SkillInvocationDetector`。
- 保留历史 `implicit` 枚举、前端渲染和 suppression 协议，避免破坏已落盘数据。
- 更新 `CONTEXT.md` 与 ADR-0013，使文档不再宣称普通文本可触发新入口。

## 实施单元

### U1. 测试固定显式入口边界

- 文件：`tests/unit/app/wplus_sop/test_entry.py`
- 场景：结构化选择仍返回 explicit；普通 SOP 文本不得运行推断器且不返回入口；正文技能标签仍不构成授权。
- 执行：先让“普通文本不得推断”测试在旧实现上失败，再实现最小修复。

### U2. 移除新入口的隐式分类

- 文件：`src/swe/app/wplus_sop/entry.py`、`src/swe/app/routers/console.py`
- 行为：分类只读取 `selected_skill_names`；普通请求直接返回普通 Chat。
- 非目标：不删除旧提议的拒绝接口、suppression 消费或前端历史卡片兼容。

### U3. 同步产品契约

- 文件：`CONTEXT.md`、`docs/adr/0013-wplus-sop-uses-persisted-session-and-structured-envelope.md`、`docs/superpowers/specs/2026-07-17-wplus-sop-workspace-design.md`
- 行为：把 W+ SOP Workspace Entry 定义为仅由受信任的显式技能选择创建；说明已有 Session 的恢复入口不受影响。

## 验证

- `tests/unit/app/wplus_sop/test_entry.py`
- `tests/unit/routers/test_console_wplus_sop_entry.py`
- Ruff/格式检查、`git diff --check`、GitNexus `detect_changes`
