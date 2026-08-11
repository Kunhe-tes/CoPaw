# Source Built-in Tools Are Source-Owned and Tenant-Executed

Source Built-in Tools are source-owned executable assets, managed only by the current source's manager or administrator from a Source Tool Library on the System Configuration page. Their scripts and version history use Swe-controlled, source-isolated storage rather than Source System Configuration JSON, Marketplace storage, or tenant workspaces. A new source tool is initially enabled for every Agent in that source, but each Agent's explicit enabled or disabled choice remains authoritative and persists across source-level deactivation and reactivation.

Default enablement is resolved lazily from the source catalog; publishing a source tool never bulk-writes tenant or Agent configuration. Only an Agent's explicit divergence from that default is persisted.

Source tools are registered through a Swe-owned adapter into the ordinary Toolkit and are exposed as part of every Agent run's initial catalog when enabled. A same-named source tool overrides only a Swe code-defined built-in and must retain that built-in's complete JSON Schema; collisions with Skill or MCP tools are rejected. Publication, replacement, and deactivation affect the next Agent run, while a run already in progress retains its initial catalog. The first release supports no browser editing, permanent deletion, rollback, tool-count quota, or Schema-complexity quota.

Source tools execute per invocation with the current tenant's workspace, declared tenant credentials, ordinary Tool Guard and approval chain, Python tenant path guard, resource limits, and a sixty-second timeout; setup failure is fail-closed. Scripts are single Python files of at most 1 MB, use no third-party dependencies, expose only statically inspectable declarations, pass a mandatory blocking safety scan, and return JSON business results that Swe normalizes into standard tool responses. Existing tool records must attribute calls to the source tool and published version without retaining parameters, script bodies, or credentials.

An active Source Built-in Tool that fails to load, violates a safety boundary, times out, or returns an invalid result produces the normal structured tool failure. An Override never falls back to the replaced code-defined built-in, because such a fallback would silently change a source-controlled behavior.

Runtime failure never automatically deactivates a Source Built-in Tool. Availability remains a source-manager decision so a transient downstream failure cannot mutate the effective catalog for every tenant.

Publication, replacement, and deactivation do not send cross-tenant notifications in the first release. The next Agent run reflects the changed effective catalog, and source-level audit records provide the authoritative change trail.

An upload becomes an unpublished draft only after static validation and mandatory safety scanning. Source managers may manually test the draft or publish it without testing; neither action is implicit. Same-name publication requires explicit source-manager confirmation, and an unconfirmed upload reports the current version identity but cannot silently replace it.

Source managers may explicitly discard an unpublished draft. This does not delete a published version or its history, while draft creation, testing, and discard remain auditable as metadata.

Each source and tool name has at most one unpublished draft. A later upload must explicitly replace or discard the existing draft so testing and publication have one unambiguous target.

Only source managers and administrators may read or download current and historical script content. Tenants can inspect the effective tool metadata for their Agents but cannot read source tool code.
