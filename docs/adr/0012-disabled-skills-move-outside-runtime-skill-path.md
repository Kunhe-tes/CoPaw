# Disabled skills move outside the runtime skill path

Workspace skill enablement is represented by both authoritative **Skill Management State** and package placement. Registered enabled packages live under `skills/`, registered disabled packages live under the sibling `.disabled_skills/`, and the manifest moves from `skill.json` to `.skill_state/manifest.json` with an explicit `layout_version`. This separates disabled packages from conventional skill registration and `skills/**/SKILL.md` discovery without introducing a platform filesystem sandbox.

**State transitions and reconciliation**

- Disabling moves the package to `.disabled_skills/` before committing `enabled=false`; enabling commits `enabled=true` before moving the package to `skills/`. A mismatch is unavailable to Agent Runs until reconciliation restores the manifest-declared state.
- If both locations contain the same registered skill, the `skills/` copy is the canonical content. It directly replaces the disabled copy, while the manifest remains authoritative for whether the canonical package ultimately belongs in `skills/` or `.disabled_skills/`.
- Editing, Pool replacement, built-in updates, or re-importing an existing disabled skill updates the disabled copy without enabling it. Deletion remains limited to disabled skills.
- Content placed manually under `skills/` without a manifest entry is unmanaged: reconciliation leaves it untouched and does not register or enable it.

**Migration**

The layout change is performed before upgrading by a deployment-side CLI, not by permanent compatibility logic or a runtime management API. The CLI provides separate `--check` and `--apply` modes, is idempotent, rejects ambiguous mixed layouts, and applies across the release scope with all-or-nothing rollback. Rollback copies exist only for the duration of `--apply` and are deleted after success. Runtime freezing and concurrent skill-write coordination during migration are outside this decision.

**Consequences**

This is **Skill Discovery Suppression**, not a **Skill Isolation Guarantee**. Ordinary registration, prompting, and `skills/**` discovery omit disabled skills, but generic file globbing such as `**/SKILL.md`, direct file access, or deliberately crafted shell commands may still discover `.disabled_skills/`; application file-tool filters and platform-level sandboxing are intentionally deferred. Existing Agent Runs also receive no immutable skill snapshot and may observe files moving after an enablement change.
