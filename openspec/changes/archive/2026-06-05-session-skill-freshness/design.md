## Context

Swe 目前会在每次 turn 启动时重新加载 session state，并在执行前调用 `runtime.agent.rebuild_sys_prompt()`，但它并不知道同一个 chat session 之前依赖过哪些技能，也不会比较这些技能当前是否已经发生目录变化、目录切换，或失去本 turn 的 effective 资格。

现有技能运行时已经具备几块可复用基础：
- `SkillInvocationDetector.start_skill()` 是技能从“可能相关”进入“已确认关联”的明确边界。
- `SafeJSONSession` 已支持 top-level session state key 的读写，`hook_overlay` 已经证明 runner-managed metadata 可以不塞进 `agent.state_dict()`。
- `SWEAgent.rebuild_sys_prompt()` 能在 session state 加载后刷新内存里的 system prompt。
- `skills_manager` 已经有技能目录解析与 `mtime`/signature 辅助函数，但本 change 需要的是轻量、跨 turn 的 freshness 检查，而不是严格内容身份。

这个 change 需要补上一条新的会话级运行时链路：在技能第一次被确认关联时建立持久化基线；在后续 turn 启动时基于当前 effective skill 解析结果比较基线；若发现有效变化，则刷新 prompt 并对模型发出一次性 notice。

## Goals / Non-Goals

**Goals:**
- 为 chat session 持久化已确认关联技能的轻量 freshness 基线。
- 仅在下一 turn 生效，不追求 mid-turn 热更新或自动中断重试。
- 用递归技能目录树最新 `mtime` 作为轻量 freshness token，控制运行时开销。
- 在 runner 的 turn 启动阶段检测技能目录变化、目录切换、effective skill withdrawal，并触发一次性 prompt refresh。
- 用一条聚合的模型内部 notice 列出本 turn 内所有受影响技能及其变化类型。
- 对缺失技能采取低噪音处理：不提示、不算变化，但清理 snapshot 中的陈旧条目。

**Non-Goals:**
- 不做严格内容签名比对，也不承诺对每一次文件内容改动都精确感知。
- 不把 low-confidence 推断加入监控集合。
- 不向用户显示技能 freshness 提示。
- 不在技能结束后立即卸载或回滚会话中已形成的关联集合。
- 不引入新的数据库、缓存服务或后台 watcher。

## Decisions

### Decision 1: 用 top-level session state key 持久化 session skill snapshot

`Session Skill Snapshot` 作为 runner-managed metadata 保存，与 `hook_overlay` 平级，不进入 `agent.state_dict()`。每个条目至少包含：
- `skill_name`
- `resolved_skill_dir`
- `freshness_token`

这样可以把会话技能 freshness 与 agent memory/formatter 状态解耦，也能用现有 `SafeJSONSession.get_session_state_dict()` / `update_session_state()` / `save_merged_state()` 路径增量维护。

Alternative considered: 把 snapshot 嵌入 `agent.state_dict()`。这会把会话运行时元数据与 agent memory/state 混在一起，增加向后兼容负担，也让 refresh 前置判断必须先反序列化 agent 内部状态。

### Decision 2: 仅在 Confirmed Skill Association 时立即写入 snapshot

只有当技能真正被 runtime 激活时，才允许它进入 `Session Associated Skill Set`。确认关联的边界沿用当前技能激活路径，例如显式声明后触发 `start_skill()`、detector 达阈值后真正激活、或读取已启用技能的 `SKILL.md` 并触发激活。

一旦发生 `Confirmed Skill Association`，同一 turn 里立刻解析技能目录并写入对应 snapshot 条目，避免“本轮使用了技能，但还没保存 freshness 基线”的窗口期。

Alternative considered: turn 结束统一回写。这样会让中途异常或提前结束导致快照丢失，下一 turn 无法判断是否相对本轮初次关联发生了变化。

### Decision 3: freshness token 使用递归技能目录树最新 mtime

这个 change 真正比较的是 `Skill Directory Freshness Token`，而不是严格 `Skill Directory Revision`。token 定义为技能目录递归树中所有受监控文件/目录的最新 `mtime`。它是启发式 change marker，不保证严格内容等价。

这让运行时只需递归 `stat` 技能树，而不必每 turn 读取并 hash 所有技能文件内容。对当前仓库里像 `docx` / `xlsx` 这类目录较大的技能，这个成本明显低于全量签名。

Alternative considered: 每 turn 做严格内容签名。它语义更强，但和用户已经确认的“轻量级、通过 mtime 过滤和筛选”目标不一致。

### Decision 4: freshness 检查放在 runner turn 启动阶段

检测入口放在 `AgentRunner` 每次 turn 启动时，`load_session_state()` 之后、`rebuild_sys_prompt()` 之前。这个边界同时具备：
- 已拿到旧 snapshot；
- 已知道当前 turn 的 request / channel / effective skills；
- 仍能在最终 prompt 固化前注入一次性 freshness notice。

变更检测包括三类：
- 同一 `skill_name`、同一 `resolved_skill_dir`，但 `freshness_token` 变化；
- 同一 `skill_name` 解析到新的 `resolved_skill_dir`，视为 directory switch；
- 之前关联过的技能本 turn 不再属于 effective skill set，视为 withdrawal。

缺失技能单独处理：若 snapshot 中的 `resolved_skill_dir` 已不存在，则继续本轮、不提示、不算变化，但静默移除该条目。

Alternative considered: 在 `SWEAgent` 内部自行检查。agent 内部缺少直接 session state 读写与 turn lifecycle 控制，难以同时处理 snapshot 装载、notice 注入与立即回写。

### Decision 5: refresh = rebuild prompt + 一次性聚合 notice

检测到有效变化后，runner 需要做两件事：
- 调整本 turn 的 request-scoped env/prompt 上下文，然后调用 `rebuild_sys_prompt()`；
- 为本 turn 注入一条 `Aggregated Skill Freshness Notice`。

notice 只给模型，不进入长期 memory 或用户可见消息。notice 的措辞保持谨慎：
- 普通 token 变化：`检测到技能目录变化`
- directory switch：写出 `old_resolved_skill_dir -> new_resolved_skill_dir`
- withdrawal：明确该技能本 turn 已不再 effective，应停止依赖基于旧技能形成的假设

Alternative considered: 只重建 prompt，不发 notice。这样模型虽然能看到新 prompt，但未必意识到要主动放弃之前对旧技能的依赖前提。

### Decision 6: 检测并注入后立即写 Applied Skill Snapshot

一旦本 turn 已经判定并应用 refresh/notice，就立刻把结果写回 snapshot，形成 `Applied Skill Snapshot`。这样同一次变化只会触发一次，不需要等 turn 完成后再提交。

对于不同变化类型的回写规则：
- token 变化：更新条目的 `freshness_token`
- directory switch：用新目录与新 token 覆盖旧条目
- withdrawal：移除对应条目
- missing skill：静默移除条目

Alternative considered: turn 成功完成后再统一回写。那会导致同一变化在异常 turn 后反复触发 notice，和本次设计追求的一次性修正语义不一致。

## Risks / Trade-offs

- [mtime 是启发式，不是严格内容身份] → 在 spec 和 notice 文案里都明确使用“检测到技能目录变化”，不宣称完成了严格内容更新比对。
- [递归 mtime 遍历仍有开销] → 仅对 `Session Associated Skill Set` 中的技能做检查，不扫描全部 enabled skills。
- [snapshot 作为 top-level session state 需要兼容旧文件] → 缺失 key 时按空 snapshot 处理，不影响已有 session 文件加载。
- [effective skill withdrawal 会改变模型前提] → 用聚合 notice 明确点名被撤回的技能，降低旧假设残留风险。
- [directory switch 会暴露内部路径到模型] → 仅在模型内部 notice 中使用，不写入用户可见消息。

## Migration Plan

1. 给 session state 增加新的 top-level snapshot key，缺失时按空值处理。
2. 在技能确认关联路径中补充 snapshot 条目即时写入。
3. 在 runner turn 启动阶段插入 freshness 检查、notice 生成、即时 snapshot 回写。
4. 扩充测试，覆盖首次关联、无变化、目录变化、directory switch、withdrawal、missing skill、聚合 notice 与一次性 notice 生命周期。
5. 回滚时可保留已写入的 top-level snapshot key；旧运行时忽略未知 key，不需要数据迁移。

## Open Questions

- None.
