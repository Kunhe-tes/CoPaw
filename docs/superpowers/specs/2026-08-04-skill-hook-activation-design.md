# Skill Hook Activation Design

## Purpose

Make skill hook activation deterministic. Incidental text in a skill document,
such as a file suffix, must never cause that skill's hooks to load or make the
skill appear in runtime attribution.

## Definitions

- A user-selected skill is a server-validated structured skill reference for a
  turn. Plain message text, including a skill name or `@` text, is not a
  selection.
- Explicit skill selection activation loads hooks only. It does not establish
  actual skill use, set the current skill, write a skill invocation trace, or
  update `skills_used`.
- Actual skill use is established only by reading the resolved `SKILL.md` or by
  a tool input that resolves under that skill's effective directory.
- File suffixes, prose-derived keywords, tool hints, tool sequences, and MCP
  server names are non-authoritative signals. Runtime must not use them to
  activate, continue, attribute, or load hooks for a skill.

## Lifecycle

### Explicit Selection

1. The request supplies a structured `context_references` skill entry, or the
   equivalent selected-skill request field.
2. The server validates the identifier, resolves the skill against the active
   workspace and channel, and confirms that its `SKILL.md` is readable.
3. After the current turn's `UserPromptSubmit` and `SessionStart` hooks have
   completed, the runner loads the selected skill's `hooks/hooks.json` into the
   session hook overlay.
4. The loaded hook source is persisted for the remaining session, including
   later requests, reconnects, and backend restarts.
5. Duplicate selection of a previously loaded skill is a no-op.

### Actual Use

1. Reading an enabled skill's resolved `SKILL.md` establishes actual skill use.
   It may load that skill's hooks if they are not already in the overlay.
2. A tool input whose resolved path is under an enabled skill's effective
   directory establishes actual skill use and tool attribution.
3. Asset-path actual use may load hooks only when that skill was explicitly
   selected earlier in the session or its resolved `SKILL.md` was read in the
   session.
4. Actual use creates the current-skill context, skill invocation trace, and
   confirmed-skill freshness snapshot.

## Hook Order

The effective order remains deterministic:

1. Tenant hooks.
2. Agent Profile hooks.
3. Selected or read skill hooks in their first-load order.

Existing hook-result merge and decision precedence rules resolve conflicts.

## Session Boundary

The hook overlay is cleared when the chat/session is cleared, a new chat is
created, or the session is terminated. A new logical session cannot inherit
selected skill hook sources from an earlier one.

## Implementation Boundaries

- Add a runner path that loads hooks from already resolved selected-skill
  directives after the two current-turn startup events.
- Separate hook loading from `SkillInvocationDetector.start_skill()` so actual
  use can be attributed without automatically loading hooks.
- Reduce `SkillInvocationDetector` to exact `SKILL.md` and resolved asset-path
  evidence for activation and attribution.
- Keep feature extraction only when it is required by non-runtime callers; no
  extracted feature may reach a runtime decision path.
- Update clear/new-session cleanup to delete the persisted hook overlay.

## Verification Matrix

| Scenario | Hook overlay | Actual use / trace |
| --- | --- | --- |
| Explicit structured selection | Loaded and persisted after startup events | No |
| Same selection repeated | Unchanged | No |
| Read resolved `SKILL.md` | Loaded if absent | Yes |
| Resolved skill asset, not selected/read | Not loaded | Yes |
| Resolved skill asset after selection/read | Already loaded or loaded | Yes |
| `.md` or any other suffix in tool input | Unchanged | No |
| Keyword, tool hint, sequence, or MCP match | Unchanged | No |
| Clear, new chat, or session termination | Removed | No inherited state |
