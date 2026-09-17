# W+ SOP 双显式入口实施计划

## 决策

新 W+ SOP 工作台入口继续只接受显式调用，但显式调用有两种等价来源：

1. Chat 技能选择器的 `selected_skill_names` 包含 `wplus-sop-miner`；
2. 用户消息正文包含独立、精确的 `@wplus-sop-miner` 提及。

正文匹配不做 SOP 语义推断，也不接受裸技能名、邮箱局部、前后缀扩展或近似名称。
两种来源都只生成进入确认卡；用户确认前不得创建 Session 或启动 Miner。

## 实施单元

1. 在 `tests/unit/app/wplus_sop/test_entry.py` 先覆盖精确提及、大小写、标点边界和误匹配。
2. 在 `tests/unit/routers/test_console_wplus_sop_entry.py` 先证明未经过技能选择器的手动 `@` 可在 Agent 运行前生成进入卡。
3. 扩展 `classify_wplus_entry` 接收已经由路由提取的用户正文，并实现精确提及判定。
4. 在 `post_console_chat` 将 `entry_text` 传入分类器；不恢复 `SkillInvocationDetector` 或模糊语义分类。
5. 同步 `CONTEXT.md`、ADR-0013 和工作台规格中的入口契约。

## 验证

- 新测试先在旧实现上失败，再实施最小修复。
- 运行 W+ entry、Console 路由和相关 W+ 单元测试。
- 运行 Ruff、Python 编译、`git diff --check` 和 GitNexus `detect_changes`。

