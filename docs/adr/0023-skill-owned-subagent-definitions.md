# Skill-owned SubAgent Definitions

Background SubAgent Definitions may be packaged by an enabled workspace Skill
as `agents/<agent-name>.toml`. A package uses a local name, while the runtime
publishes the Definition under the Skill-qualified name
`<skill-name>:<local-name>`. That qualified name is exclusively owned by its
Skill; Stored Definitions cannot claim it, and custom Definitions cannot claim
an existing built-in name.

Only a Main Agent turn whose user message explicitly requests a SubAgent
receives Background SubAgent tools. When that gate is open, the
`start_subagent` tool describes available Skill-owned Definitions using their
qualified names, descriptions, and trigger keywords. The Main Agent selects an
exact name. Its `objective` and optional `background` are combined with the
Definition instruction for the worker prompt. The Definition instruction and
fixed runtime safety rules are trusted system content; `background` is bounded
as explicitly untrusted task material in that system message, while `objective`
is a structured user message. A caller-supplied instruction is retained solely
for an unknown-name run-scoped fallback and never overrides a resolved
Definition.

Each Skill-owned Definition declares its optional Skill dependencies. Its
optional `mcps` field narrows MCP inheritance: when present, the worker loads
only the named parent-enabled MCP clients; when omitted, it inherits every
parent-enabled MCP client. `mcps = []` explicitly inherits none. Unavailable
Skills, MCP configuration, and failed MCP connections are silently omitted.
MCP clients connect independently in the worker from a launch snapshot of the
parent Agent configuration. Declared Skill dependencies use the ordinary Skill
Toolkit registration path, not inlined Skill documents.

Skill-owned Definitions inherit the parent Agent's enabled built-in tools by
default. Optional `allow` and `deny` settings narrow that candidate set.
Run-scoped Definitions inherit the same parent-enabled built-in candidate set,
and all parent-enabled MCP clients, but have no Definition-level tool or MCP
override. Every operation remains governed by the effective SubAgent policy,
Tool Guard, and approval policy. A Background SubAgent cannot begin an
interactive approval flow: an operation requiring approval is rejected unless
it is already preapproved or automatically allowed. SubAgents cannot delegate
further.

Only Skill-owned Definitions may optionally select a configured tenant model by
provider and model identifier, including an eligible local model. An unavailable
reference silently falls back to the parent model; built-in, Stored, and
run-scoped Definitions always inherit the parent model. Optional Skill-owned
budgets may only remain within platform limits.

At run start, the runtime persists an immutable launch snapshot containing the
resolved Definition, dependencies, MCP configuration, and model selection.
Later Skill lifecycle, package, MCP, or model changes do not affect that run.
Launch diagnostics are retained for detailed run inspection only; ordinary
parent-facing result projections remain compact. An invalid Definition package
is omitted without disabling its owning Skill or sibling packages, while the
ordinary Skill security scan continues to apply to the whole package.

This chooses explicit, Skill-scoped Skill capability declarations and an
optional Skill-owned MCP restriction over inheriting the whole workspace Skill
set. It permits specialized agents to use Skills, MCPs, selected models, and
parent-bounded file changes without giving a worker implicit access to
unrelated workspace Skills or mutable runtime configuration.
