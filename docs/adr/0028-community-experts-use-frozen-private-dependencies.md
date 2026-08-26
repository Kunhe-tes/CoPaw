# Community Experts use frozen private dependencies

Community Experts are source-scoped Marketplace packages, received into an Agent Profile as an independently managed expert. Each published version freezes its declared Skill and MCP content; selected execution exposes only that private dependency view for the Chat and never installs or merges the resources into the Agent Profile. This preserves package reproducibility and isolation while allowing administrators to distribute, unpublish, or withdraw packages under the existing Skills and MCPs Marketplace permission convention.

## Consequences

Users explicitly select one enabled received or local expert for a message; Main Agent routing never discovers experts implicitly. Administrators alone publish, version, distribute, unpublish, and withdraw; user installation is Profile-scoped and cannot self-update. A withdrawal stops later runs immediately but lets an in-flight run finish, while updates can silently replace an existing received copy of the same community item.
