## Why

会话中的技能依赖现在只在技能被激活的当下生效，后续 turn 不会感知这些技能目录是否已经变化、切换到新的目录绑定，或失去当前 turn 的 effective 资格。这会让同一个 chat session 在后续 turn 里继续沿用基于旧技能内容形成的假设，导致 prompt 与实际技能状态脱节。

现在补上会话级技能 freshness 机制，可以让运行时在不追求 mid-turn 热更新的前提下，在下一 turn 开始前检测关联技能的目录变化并刷新 prompt，使模型重新以当前技能内容为准。

## What Changes

- 为 chat session 引入 top-level 的 session skill snapshot，持久化当前 session 已确认关联过的技能、解析到的技能目录，以及轻量级 freshness token。
- 仅监控当前 session 已确认关联的技能，不扫描所有 enabled skills，也不把低置信度推断加入监控集合。
- 在 turn 启动阶段、`load_session_state()` 之后且 `rebuild_sys_prompt()` 之前，比较 snapshot 与当前 effective skill 解析结果，检测技能目录变化、目录切换或 effective 资格撤回。
- 当检测到有效变化时，刷新本 turn 的 prompt，并向模型注入一条仅本 turn 生效的聚合 freshness notice，逐项列出受影响技能及变化类型。
- 对缺失的关联技能采用静默移除策略：不触发 refresh 或 notice，但从 snapshot 中删除陈旧条目。
- 为 freshness token、snapshot 读写、turn 启动 refresh、directory switch、effective skill withdrawal 与 notice 聚合补充回归测试。

## Capabilities

### New Capabilities

- `session-skill-freshness`: Define how a chat session tracks associated skills across turns, detects next-turn skill-directory changes, refreshes prompt state, and emits a model-only freshness notice.

### Modified Capabilities

- None.

## Impact

- Affected code:
  - `src/swe/app/runner/runner.py`
  - `src/swe/app/runner/session.py`
  - `src/swe/agents/react_agent.py`
  - `src/swe/agents/skill_invocation_detector.py`
  - `src/swe/agents/skills_manager.py`
  - tests under `tests/unit/app/` and `tests/unit/agents/`
- Session state schema changes:
  - Add a new top-level session state key for the session skill snapshot.
- No external API contract, database migration, or third-party dependency changes are expected.
