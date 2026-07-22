# 禁用技能发现抑制设计

**Goal:** 将已登记但禁用的技能移出 Workspace 的常规 `skills/` 路径，避免它们参与技能注册、提示注入和 `skills/**/SKILL.md` 发现。

**Architecture:** Workspace 使用清单作为启停状态权威，并用两个同级目录物化状态：`skills/` 保存启用包，`.disabled_skills/` 保存禁用包。管理面根据清单解析实际包位置；运行面只从 `skills/` 解析已登记且启用的技能。旧布局通过发布前独立 CLI 一次性迁移，运行时不保留旧布局兼容逻辑。

**Tech Stack:** Python、FastAPI、文件锁与原子 JSON 替换、pytest

---

## 目标布局

```text
workspace/
├── skills/                    # 已登记且启用的技能包
├── .disabled_skills/          # 已登记且禁用的技能包
└── skill.json                 # Skill Management State
```

Workspace 继续以现有 `skill.json` 作为唯一权威清单。该文件由 CoPaw 和外部服务共同读写；外部服务会保留不识别的字段，因此清单可增加独立的 `layout_version: 2`。现有随写入递增的 `version` 继续表示内容修订，不能用于推断布局版本。不创建 `.skill_state/manifest.json`，也不在两个清单之间双写。

当 `skill.json` 不存在时，Market 的首次分发或显式 claim 可通过既有共享写入器创建默认 v2 Workspace 清单。对于预先存在的清单，Market 仅在其布局为完整且受支持的 v2、结构正确时执行有副作用操作；仅预先存在且不可读或结构错误、缺失 `layout_version`、或版本不支持的清单必须失败并提示先运行 CLI，不得隐式升级该清单，也不得复制、覆盖或删除技能目录。

Skill Pool 的目录和清单布局不在本次变更范围内；只有 Workspace 技能布局变化。

## 运行时与管理边界

- Agent 注册、提示注入、有效技能解析和 hook 加载只接受清单中 `enabled=true` 且实际位于 `skills/<name>` 的技能。
- 技能管理 API/UI 对已登记技能根据清单状态解析技能包位置，因此仍可查看和编辑禁用技能的 `SKILL.md`、`references/`、`scripts/` 和配置。
- 已登记技能的删除仍只允许作用于禁用技能，并同时删除其解析到的包目录与清单条目；Market 保留对未登记普通目录的既有直接删除，且不创建清单条目。
- Pool 替换、内置技能更新、重新导入或管理面编辑同名禁用技能时，只更新 `.disabled_skills/<name>`，不得隐式启用。
- Market 在首次分发、更新启用技能或删除技能后触发现有 Agent reload；仅维护禁用技能时不触发 reload。
- 清单中没有条目的 `skills/<name>` 属于 Unmanaged Skill Content。协调逻辑不移动、不登记、不启用也不删除它；但若它与已登记禁用技能同名，则适用 active collision promotion。
- Market 可继续展示和维护普通 `skills/` 中的 Unmanaged Skill Content；仅当用户显式执行启用且通过既有安全扫描时，Market 才将其登记为启用技能。例外是与已登记禁用技能同名时，SWE 协调和 Market 管理操作均删除旧 `.disabled_skills/<name>` 并将登记技能置为启用。`.disabled_skills/` 不接纳未登记内容。

## 启停状态转换

清单是启停状态的权威来源，目录位置是状态的物化结果。API 只有在全部步骤成功后才返回成功。

### 禁用

1. 若 `.disabled_skills/<name>` 已存在，先删除旧副本。
2. 将 `skills/<name>` 移至 `.disabled_skills/<name>`。
3. 原子写入清单，将 `enabled` 更新为 `false`。
4. 触发现有 Workspace Agent 重载机制。

### 启用

1. 原子写入清单，将 `enabled` 更新为 `true`。
2. 将 `.disabled_skills/<name>` 移至 `skills/<name>`。
3. 触发现有 Workspace Agent 重载机制。

这个非对称顺序保证转换中断时只出现“清单认为启用，但运行目录暂时缺包”的失败关闭状态，不出现“清单认为禁用，但包仍在常规运行目录”的状态。

## 协调规则

协调在构造运行视图前完成，且只处理清单中已登记的技能：

| 清单状态 | `skills/<name>` | `.disabled_skills/<name>` | 结果 |
|---|---:|---:|---|
| enabled | 有 | 无 | 保持 |
| enabled | 无 | 有 | 移至 `skills/` |
| disabled | 无 | 有 | 保持 |
| disabled | 有 | 无 | 移至 `.disabled_skills/` |
| 任意 | 有 | 有 | 以 `skills/` 内容为准，删除禁用副本并将登记技能置为 enabled，保留在 `skills/` |
| 任意 | 无 | 无 | 删除陈旧清单条目，沿用现有语义 |

协调期间的不一致技能不可加入 Agent 的有效技能集合。目录移动和清单写入继续复用现有跨进程文件锁及原子 JSON 替换能力；本次不引入 Agent Run 技能快照。

外部服务直接修改 `skill.json` 的 `enabled`、`config` 或元数据后，CoPaw 在下一次协调时保留这些修改，并根据 `enabled` 物化目录位置。CoPaw 内部继续使用 `.skill.json.lock` 与原子替换；跨服务并发写入协调暂不处理。

## 一次性迁移 CLI

发布流程在切换到新版本前运行部署侧 CLI；不提供运行时管理 API，也不在主流程运行迁移逻辑。

```text
swe skills migrate-layout --check
swe skills migrate-layout --apply
```

`--check` 只读检查发布范围内所有 Workspace：`skill.json` 可解析、技能路径合法、目标目录没有无法解释的混合状态、目录可写且迁移计划完整。如果意外存在 `.skill_state/manifest.json`，按混合布局直接拒绝。任一检查失败时返回非零状态，不修改文件。

`--apply` 在原路径就地升级 `skill.json`：只移动清单中 `enabled=false` 的已登记技能，保留全部清单字段，并写入 `layout_version: 2`。命令不改名、删除或复制 `skill.json`，也不创建 `.skill_state`。已带 `layout_version: 2` 且布局一致的 Workspace 报告 `already_migrated`；失败并成功回滚的 Workspace 可安全重试。执行前创建仅供本次命令使用的临时回滚副本，任一 Workspace 失败则恢复全部已修改 Workspace 的目录与原始 `skill.json`，全部成功则立即删除副本。

迁移期间的运行时冻结和并发技能写入协调不在本次范围内，由部署操作规程规避。

## 明确的安全边界

本次提供 Skill Discovery Suppression，而不是 Skill Isolation Guarantee：

- 禁用技能不再位于 `skills/`，不参与注册、提示和常规 `skills/**` 发现。
- 不修改普通文件工具的路径过滤，也不引入平台级文件系统沙箱。
- `**/SKILL.md`、显式文件路径或刻意构造的 shell 命令仍可能发现 `.disabled_skills/`。
- 现有 Agent Run 不持有不可变技能快照，启停发生后可能观察到文件移动。

一期验收不能表述为“模型无法读取禁用技能”，只能表述为“已登记且禁用的技能移出常规技能路径并退出 Agent 注册与提示”。

## 错误处理

- 启停源目录缺失、移动失败或清单写入失败时返回失败，不报告部分成功。
- `skill.json` 无法解析时失败关闭：不注册相关技能，不移动目录，也不覆盖外部服务写入的损坏文件。
- 清单与目录不一致时，技能保持不可用，协调逻辑按清单恢复；同名 active/disabled 双副本是例外，适用 active collision promotion。
- 管理面不得因禁用包位于隐藏目录而返回“技能不存在”。
- Market 的 reload 通知失败不回滚已经完成的业务写入；记录可观察告警，后续 SWE 协调或启动收敛运行视图。
- 迁移 CLI 输出每个 Workspace 的检查、迁移、回滚或跳过结果，并以非零退出码表示任何未恢复错误。

## 测试策略

- 路径与清单单元测试确认 Workspace 始终使用 `skill.json`，不创建 `.skill_state/manifest.json`，并覆盖 `layout_version` 与启用/禁用位置解析。
- TDD 行为测试覆盖禁用、启用、重复副本覆盖、失败关闭协调、未知目录忽略、禁用技能编辑、删除和 Pool 更新保持禁用。
- 外部服务兼容测试模拟读取原 JSON、保留未知字段并修改 `enabled`、`config` 或元数据，然后验证 CoPaw 协调目录且保留这些修改。
- CLI 测试覆盖 `--check` 无写入、`skill.json` 就地升级、已迁移幂等、混合状态拒绝、中途失败全量回滚和临时副本清理。
- 回归测试确认有效技能解析、Agent 注册、hook 加载和 Workspace 重载继续只处理启用技能。
- Market、Pool、Agent 创建、租户种子和技能管理路由回归确认共享 `skill.json` 合同不变；`skill_pool/skill.json` 行为保持不变。

## 不在范围内

- 平台级文件系统沙箱、容器挂载隔离或按 Agent 创建独立安全视图。
- 对 shell、glob、grep、文件树或显式文件读取增加 `.disabled_skills` 拒绝规则。
- 运行时旧布局兼容、后台迁移、懒迁移、迁移管理 API 或技能写入冻结。
- CoPaw 与外部服务的跨进程锁协议、并发写入冲突检测或字段级合并。
- 长期迁移备份、冲突副本归档或 Agent Run 级不可变技能快照。
