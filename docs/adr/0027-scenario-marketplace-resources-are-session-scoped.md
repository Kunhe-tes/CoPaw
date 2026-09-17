# Scenario marketplace resources are session-scoped

Scenario Presets may provisionally make their configured marketplace Skills and MCP resources available for the current Chat session when the tenant or Agent lacks a persistent copy. The preset stores stable market resource identities and each new Chat session resolves the latest eligible version into an immutable Session Marketplace Resource Snapshot; market updates do not hot-reload an active session. The temporary view lasts until that Chat session ends, is not written to tenant or Agent configuration, and remains subject to normal resource validation, current-tenant credential resolution, Tool Guard, and approval controls; this preserves multi-turn scenario continuity without turning a preset selection into permanent installation, cross-tenant credential transfer, or authorization.

When an existing Chat is reopened, its saved snapshot is restored rather than resolving the preset or market latest versions again. Invalidated resources or credentials are marked unavailable in place, without rewriting the remaining snapshot entries.

If a market resource is unavailable when a new session initializes, its Scenario Preset is retained and binds any remaining available resources without a terminal-user warning. The Source administrator repairs the binding explicitly through management surfaces and diagnostics; market lifecycle changes never delete or rewrite a preset automatically.

Scenario Presets bind marketplace MCP services as whole services, not individual tools. The session-scoped view exposes the selected service's callable tool set while retaining normal tenant credential resolution, Tool Guard, and approval controls.

Each selected MCP service's callable tool set is discovered and frozen in the Session Marketplace Resource Snapshot at session initialization; service-side changes take effect only for later Chat sessions.

A selected marketplace Skill is activated at scenario-session initialization with the same trusted Skill-use instruction semantics as an explicit `@Skill` selection, without a visible user-message marker. It stays available for later messages in the same Chat without duplicating the instruction block.

When the current tenant or Agent already has a corresponding persistent Skill or MCP configured, that configured resource is preferred. A temporary marketplace resource view is created only for a missing persistent resource, and the session snapshot records which source and version were actually used.

Selecting a preset does not install, connect, or resolve resources. The first-message submission is the authoritative boundary: the backend re-resolves the current catalog entry, resource bindings, persistent-resource preference, credentials, and latest eligible market versions, then atomically creates the session snapshot.

The Session Marketplace Resource Snapshot is stored in existing Chat metadata solely for later Chat recovery. Successful initialization also emits a structured application log containing only the Source, Chat, catalog-node IDs, and actual resource snapshot sources, versions, and availability outcomes; it excludes prompt content, packaged Skill content, and credentials and creates no separate audit file, database, or usage aggregate.
