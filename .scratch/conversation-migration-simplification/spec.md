# Simplified Source-Isolated Conversation Migration

Status: open
Type: task
Triage: ready-for-agent

## Problem Statement

The source-isolated `prepare` and `migrate --apply` workflow repeats expensive source discovery, semantic inventory, hashing, and full-source rechecks. A large migration can spend most of its runtime reviewing files that `prepare` already checked. The migration also binds every SQL query to one physical connection because the schema-level named lock and lock guard are coupled to that connection, even when deployment guarantees that only one migration process can run.

## Solution

Keep the two operator-facing commands while assigning each a single responsibility. `prepare` discovers and checks the immutable source once, records the frozen source mapping and each workspace's `chats.json` modification time, then performs the database schema preflight. `migrate --apply` prunes SQL-published sources before source-file access, parses each remaining workspace once into the existing bounded transient importer records, and imports those records into SQL and NAS bundles. It compares `chats.json` modification times at the start and before publication, and retains target-side verification.

The new protocol relies on the deployment guarantee that only one migration process can operate on an application schema at a time. Migration queries may use different physical connections; transactions remain pinned to one connection, and every connection must resolve to the frozen database server UUID and schema. Existing manifests and jobs retain their current lock, digest, and retry behavior.

## User Stories

1. As a migration operator, I want `prepare` to discover service, tenant, source, Agent, and workspace identities once, so that a large source tree is not repeatedly rediscovered.
2. As a migration operator, I want `prepare` to validate and inventory the fixed conversation inputs once, so that malformed or unsafe source data is reported before import.
3. As a migration operator, I want the manifest to record each workspace's `chats.json` modification time, so that the migration can detect changes to the conversation registry without hashing all input files.
4. As a migration operator, I want `prepare` to omit per-input content digests, so that preparation avoids an extra full read solely for hashing.
5. As a migration operator, I want `migrate` to use the frozen manifest mapping, so that source identity is not silently re-derived from changed configuration.
6. As a migration operator, I want `migrate` to read SQL publication state and prune published sources before opening their old files, so that live data from an already released source is never re-imported or overwritten.
7. As a migration operator, I want each unpublished workspace to be parsed once into bounded transient records consumed by the importer, so that migration does not repeat a preflight inventory and then reread the same session bodies for import.
8. As a migration operator, I want a source whose `chats.json` mtime differs from prepare's recorded value to remain unpublished, so that a changed conversation registry cannot be migrated under stale evidence.
9. As a migration operator, I want source-specific failures to remain isolated, so that one invalid or unavailable source does not prevent independent sources from completing and publishing.
10. As a migration operator, I want committed SQL tickets and bundle publication state to support unchanged-input retries, so that an interrupted source can resume without duplicating or rebinding imported records.
11. As a migration operator, I want the migration to retain target SQL and bundle verification, so that publication still requires the imported result to satisfy the storage contract.
12. As a migration operator, I want the migration to accept different physical connection IDs while enforcing the expected server UUID and schema, so that ordinary connection-pool rotation does not appear as lock loss.
13. As a migration operator, I want every transaction to stay on one physical connection and every pooled connection to be checked against the target database identity, so that connection rotation does not split transactions or route writes to another database.
14. As a deployment operator, I want the single-process-per-application-schema guarantee to cover every migration entry point and host, so that removing the database named lock does not permit concurrent migration owners.
15. As an operator continuing an existing migration, I want its existing manifest and SQL binding to retain their original protocol, so that a new freshness policy cannot silently change an in-flight job.

## Implementation Decisions

- The publication unit remains `(service_unit_id, tenant_id, source_id)`. All Agents and workspaces in one source continue to pass or fail together; other sources may publish independently.
- `prepare` performs one source discovery and semantic inventory pass, captures `chats.json` `st_mtime_ns` per workspace, and checks the mtime before and after reading that workspace. A mismatch, missing required registry, unsafe path, symlink, unsupported object, or invalid conversation input fails the owning source or shared scope as appropriate.
- The frozen manifest stores the established identity/path mapping, inventory summaries needed for reconciliation, the chats mtime observations, and a versioned freshness-protocol marker. It does not store full parsed conversation bodies, a durable inventory spool, or per-input content digests.
- `migrate --apply` reads publication states from SQL before accessing source files. Published sources are pruned from source processing. For each unpublished source, the importer compares each workspace's current chats mtime with the manifest, traverses the manifest-bound files once into bounded transient workspace records, then consumes those records through the existing journal, SQL, and bundle protocols. The transient records are not persisted in the manifest and are discarded after the source completes.
- Migration retains path containment, no-follow filesystem checks, source byte and per-file budgets, stable ticket identities, transaction boundaries, uncertain-commit handling, bundle durability, source failure isolation, target schema checks, and fast target-side verification.
- The final source stability check compares only the recorded `chats.json` mtime values. It does not re-discover configuration, perform a second inventory pass over `sessions/` or `dialog/`, or compute content digests. The deployment must keep all unpublished conversation inputs and configuration evidence read-only and unchanged from prepare through publication. The mtime check is not a content-integrity proof for files outside `chats.json`.
- Automatic source re-review is removed from ordinary migrate. A retry may continue only with the existing frozen evidence and unchanged inputs. Accepting corrected input requires an explicit reviewed preparation revision limited to unpublished sources with no committed business rows or migration tickets; it must preserve migration identity and published-source evidence. Existing jobs with committed tickets cannot be rebound.
- The new manifest protocol is versioned so older manifests continue using their established connection lock, digest, source review, and retry semantics. Existing jobs cannot be converted by editing their manifest or clearing SQL control rows.
- For new source-isolated jobs, the schema-wide named lock and fixed `CONNECTION_ID()` invariant are replaced by the externally guaranteed single migration process per application schema. The database guard checks server UUID and schema identity without requiring the same connection ID or `IS_USED_LOCK` owner. Each transaction remains connection-pinned, and pooled connections must be rejected if their server UUID or selected schema differs from the job binding.
- The external singleton guarantee must cover all migration commands, retry processes, hosts, and deployment entry points that can write the same application schema. If that guarantee is unavailable, the named lock remains required.
- No business-table or source-publication schema change is required. Historical shares remain excluded from migration input; existing source publication and DBA finalization contracts remain in force.

## Testing Decisions

- The primary seam is an end-to-end `prepare` then `migrate --apply` workflow against isolated MySQL and local source/NAS roots. Tests should assert externally visible reports, source publication states, SQL rows, bundle availability, and safe retry behavior rather than private helper calls.
- Workflow coverage should prove prepare records per-workspace chats mtimes and reports invalid source input; migrate rejects a changed chats mtime, skips a published source without opening its old inputs, streams unpublished source data, verifies target output, and independently publishes successful sources.
- Connection identity tests should provide different connection IDs with stable server UUID/schema and expect success, then vary server UUID or schema and expect a global stop. Transaction tests should ensure all statements in a transaction use one connection.
- Failure tests should cover a source read/parse failure, an interruption after ticket creation, an unknown commit result, a chats mtime change before publication, and a retry with unchanged inputs. Published source data must remain untouched in each case.
- Existing tenant/source workflow MySQL tests and migration lock guard tests are prior art. Legacy-manifest tests must continue to prove their existing lock and digest behavior.
- A deployment-facing test or release check must verify that the external single-process guarantee covers every writer of migration control state; unit tests cannot establish that operational property.

## Out of Scope

- Removing target-side SQL, bundle, ownership, or publication verification.
- Detecting content changes to `sessions/`, `dialog/`, configuration evidence, or other inputs through application-side hashes or a second full re-inventory. Their immutability is an operational prerequisite for this protocol.
- Concurrent migration processes or source-level distributed locks.
- Automatically accepting corrected inputs after prepare without an explicit audited revision.
- Converting existing manifests or jobs to the new freshness and connection protocol.
- Changing conversation business tables, runtime source admission, historical-share migration scope, or DBA publication finalization.

## Further Notes

The source worktree's current operational guide and accepted source-publication ADR define the existing source identity and independent publication semantics. This specification narrows source freshness and connection ownership for new jobs only. The currently observed job with 637 discovered sources and zero migration tickets remains governed by its existing manifest contract and must not be silently switched to this protocol.
