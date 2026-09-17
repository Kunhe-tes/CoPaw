# 可续跑的 Workspace 技能布局迁移

**Goal:** 让 `swe skills migrate-layout --apply` 清理废弃技能登记并在失败后可直接续跑，同时不再创建 Workspace 全量备份或执行回滚。

**Architecture:** 迁移继续以 `skill.json` 为权威清单，并原子写入该文件。预检将缺少 `SKILL.md` 的已登记技能视为废弃条目；应用阶段从清单中移除这些条目，再将其余禁用技能迁移至 `.disabled_skills/`，最后写入 `layout_version: 2`。不复制整个 Workspace；一次运行中某个 Workspace 失败时立即抛出，先前已完成的 Workspace 保持完成状态。

## 行为

- 旧布局的已登记技能在 `skills/<name>/SKILL.md` 和 `.disabled_skills/<name>/SKILL.md` 都不存在时，为陈旧登记。`--check` 不修改文件且不因该状态失败；`--apply` 从 `skill.json["skills"]` 删除该条目。
- `--apply` 保留未登记目录，不创建占位 `SKILL.md`，也不针对任何具体技能名作特殊处理。因此当前缺失的 `summarize` 会被清理，但相同行为适用于所有废弃登记。
- 已登记的符号链接、同一技能在两个受管目录中同时出现、启用技能位于禁用目录等状态仍为错误，不能通过删除清单条目绕过。
- 不再创建临时 Workspace 副本，不执行目录/清单恢复，也不报告回滚结果。`skill.json` 继续使用已有的原子替换，避免损坏单个清单写入。

## 可续跑语义

迁移按确定的 Workspace 顺序逐个应用。任一 Workspace 在移动目录或写清单时失败，命令立即返回非零，已经成功迁移的 Workspace 不回滚。

旧清单尚未写入 `layout_version: 2` 时，允许已登记且禁用的技能包已经位于 `.disabled_skills/<name>`，只要该技能没有同时出现在 `skills/<name>`，且其包完整。该状态表示此前运行在写入最终清单前中断；后续 `--apply` 跳过已经移动的包、完成剩余移动并原子写入版本。再次执行因此从未完成的 Workspace 继续，而已完成的 Workspace 报告 `already_migrated`。

## 测试

- 缺少已登记技能文档的旧清单可通过检查；应用后该条目已删除，其他技能照常迁移。
- 未登记目录不受影响，符号链接和不一致的受管双副本仍被拒绝。
- 故意使第二个 Workspace 的应用失败：第一个 Workspace 保持迁移成功，命令立即停止，不调用备份或恢复；修正失败条件后再次应用，第二个 Workspace 完成且第一个保持幂等。
- 故意在一个 Workspace 移动首个禁用包后失败：再次应用能够接受中间目录状态并完成迁移。
