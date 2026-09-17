# Agent-owned SubAgent Experts

## Purpose

Users configure reusable experts for exactly one Agent Profile in the expert
center. The Main Agent can select enabled experts on a later user turn, while
active SubAgent runs keep their launch snapshots.

## Ownership and persistence

An Agent-owned Definition Package is stored at
`~/.swe/<tenant-id>/workspaces/<agent-id>/agents/<definition-id>.toml`.
`definition-id` is an opaque stable UUID used by management APIs and audit
records. The TOML `name` is the editable, exact Main-Agent selection name.
The package keeps unsupported TOML fields on structured edits, but neither the
form nor runtime interprets those fields.

The three reusable sources are built-in, Agent-owned, and Skill-owned. The
expert center only lists and manages Agent-owned packages. A fourth source,
run-scoped, exists only for an unknown exact name accompanied by an explicit
instruction.

## Lifecycle and API

Creating a package produces `enabled = false`. Updating its structured fields
does not change enablement. Enabling, disabling, and deleting are distinct
revision-protected mutations. Each mutation supplies an `If-Match` revision;
conflicts produce HTTP 409. Enablement rejects invalid TOML and reserved or
active Agent-owned name collisions. A missing dependency is a warning, not an
invalid package. An invalid package can be replaced through the form or
deleted.

The API resolves Agent identity from the existing request context and never
accepts a user-selected workspace path. It returns canonical generated TOML
and validation errors so the UI can remain structured and read-only with
respect to raw TOML.

## Runtime

At Main-Agent turn construction, the runtime combines built-in definitions,
enabled valid Agent-owned packages, and definitions from effective Skills.
The `start_subagent` tool lists exact names, descriptions, and keywords without
source labels. It resolves only exact names. An unresolved name has the
existing run-scoped fallback only if an `instruction` was provided.

Agent-owned definitions share Skill-owned capability semantics: parent-enabled
built-ins and MCPs are candidates by default; a declared MCP list narrows MCP
access; declared Skills load only when parent-enabled; unavailable references
are silently omitted; an unavailable model falls back to the parent model.
SubAgent Definition snapshots identify `builtin`, `agent_owned`,
`skill_owned`, or `run_scoped`.

## Console

`/experts` is a Creation Center route. It lists only Agent-owned definitions,
has an empty state and create action, supports edit/repair, separate enablement
and deletion actions, and shows warnings for currently unavailable dependencies
or model references. It does not offer a trial execution button. Existing
effective-Skill, MCP, and provider endpoints supply form options.

## Verification

Tests prove TOML preservation/validation, stable file identities, revisions,
enablement collisions, runtime catalog composition and exact lookup, capability
inheritance, snapshot sources, API status behavior, and the console's stateful
form interactions.
