---
status: accepted
---

# Conversation Migration Publishes Tenants Independently

On 2026-11-13 the user selected independent rollout for successful tenants while failed tenants remain unavailable and can be repaired and migrated later. A publication unit contains every source, Agent, workspace and permanent share belonging to one `(service_unit_id, tenant_id)`; partial import is never sufficient to publish that unit. One tenant's data failure must not prevent unrelated, provably independent tenants from completing.

This supersedes ADR 0044's all-production-scopes-at-once decision and ADR 0045's requirement to keep all new-version traffic stopped until every tenant completes. Legacy writers must still drain and exit before the immutable migration source is captured. There is no fallback to legacy, dual write or incremental catch-up. Failed or unknown tenants remain closed; already published tenants must retain new committed writes during subsequent retries and rollback. ADR 0045's consistency and complete rollback export requirements continue to apply.

The tenant publication gate is implemented and validated with local directories and isolated MySQL schemas. Production NAS, large-scale performance and fixed old-image rollback acceptance remain separate release gates. See the [implementation design](../superpowers/specs/2026-11-13-conversation-tenant-cutover-design.md) and [operations guide](../superpowers/plans/2026-11-13-conversation-tenant-migration-operations.md).

On 2026-11-14 the user explicitly selected in-place migration: `source_root`, `config_root`, `snapshot_root` and `original_root` are identical, while `nas_root` remains independent. This requires explicit `--tenant-isolation --in-place`, durable mode binding, nonoverlapping tenant ownership, and immutable unpublished conversation/configuration inputs. Published tenants may resume writes without reopening unpublished tenants; migration and evidence review must skip their live inputs. Shared root metadata is not tenant evidence. Exact evidence files and conversation entry membership remain checked, and restored evidence must be included when stabilizing retry ownership boundaries. Legacy writers still stay stopped; this decision introduces no dual write or incremental catch-up.
