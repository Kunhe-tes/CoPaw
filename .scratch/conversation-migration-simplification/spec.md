# Simplified Source-Isolated Conversation Migration

Status: open
Type: task
Triage: ready-for-agent

## Problem Statement

The current two-stage migration performs conversation discovery and semantic inventory during `prepare`, then reads the conversation inputs again during `migrate`. This makes prepare scan `chats.json`, sessions, dialog, and ledgers even though its durable purpose is to freeze the service, tenant, source, Agent, and workspace mapping. The current mtime checks also imply a prepare-time input snapshot contract that operators do not need: they already stop writers and keep unpublished inputs unchanged through migration.

## Solution

Keep the two operator-facing stages. `prepare` discovers and freezes service/configuration identity, tenant/source ownership, Agent and workspace locations, validates structural path ownership, and runs the target database preflight. It does not parse conversation data, semantically inventory workspace contents, record chats mtimes, or calculate source-input digests.

`migrate --apply` queries SQL publication state first and skips published sources before opening their old inputs. For each unpublished source, it scans each mapped workspace once, performs the existing bounded safety and semantic inventory into temporary records, then gives those records to the existing importer for SQL and NAS writes. It verifies the target and publishes the source independently. The importer remains scan-then-write; streaming source records directly into SQL is not part of this change.

No prepare-to-migrate file-change detection is performed. The operational precondition is that all unpublished conversation inputs, identity configuration, and the frozen manifest mapping remain unchanged from prepare through publication. No manifest binding digest, source input digest, chats mtime comparison, or temporary inventory checksum is introduced for this workflow. Source publication state remains authoritative in SQL. The jobs table stores only its small manifest storage-mode marker; the complete mapping remains in the manifest, which migrate copies beside the per-service runtime references.

## User Stories

1. As a migration operator, I want prepare to identify service, tenant, source, Agent, and workspace mappings without parsing conversation bodies, so that preparation time is spent on identity discovery and database readiness.
2. As a migration operator, I want prepare to validate service roots and record workspace ownership, while deployments guarantee source paths do not overlap.
3. As a migration operator, I want the manifest to record every workspace position and its resolved identity, so that migrate consumes a fixed mapping instead of rediscovering identity from mutable configuration.
4. As a migration operator, I want prepare to omit semantic parsing of `chats.json`, sessions, dialog, and turn ledgers, so that those inputs are scanned only during migrate.
5. As a migration operator, I want prepare to run database schema preflight without creating business rows or publishing a source, so that I can catch target setup errors before migration.
6. As a migration operator, I want migrate to query SQL publication state before touching source files, so that already-published sources are skipped without reading their old workspaces.
7. As a migration operator, I want migrate to scan each unpublished source's workspaces once into bounded temporary records, so that source files are not semantically inventoried once in prepare and again in migrate.
8. As a migration operator, I want the existing importer to consume those temporary records after scanning, so that source parsing stays bounded and established SQL ticket and bundle behavior is retained.
9. As a migration operator, I want malformed, missing, unsafe, or oversized input to fail only its owning source, so that independent sources can still migrate and publish.
10. As a migration operator, I want SQL and NAS writes to begin after the source scan succeeds, so that scan-time input failures do not unnecessarily leave partially imported source data.
11. As a migration operator, I want source publication to happen only after target verification, so that a source is admitted only after its imported records and bundles satisfy the storage contract.
12. As a migration operator, I want retry to use the same manifest mapping and SQL tickets, so that interrupted imports can reconcile without reallocating identities or rebinding records.
13. As an operator, I want published sources skipped and failed sources left unpublished, so that partial migration does not overwrite online data or expose incomplete source state.
14. As an operator, I want no mtime or digest comparison between prepare and migrate, so that the procedure does not rescan inputs for change detection already covered by the writer-stop and read-only operational boundary.
15. As an operator, I want the jobs row not to contain every tenant and workspace mapping, so that row size remains bounded as source count grows.
16. As a service operator, I want the installed runtime reference and colocated manifest to supply the complete service mapping, so that runtime admission does not need a large database JSON field or a new environment variable.
17. As a deployment operator, I want all service instances to use the same frozen manifest for this migration, so that workspace identity and source boundaries remain consistent across instances.
18. As an operator, I want target-side SQL and bundle verification retained, so that simplifying source handling does not weaken publication criteria.
19. As an operator, I want the existing singleton migration-process deployment guarantee retained, so that no additional database lock or source-level distributed lock is required.
20. As a migration operator, I want normal source-level failure isolation retained, so that one source's parse failure does not stop unrelated sources.

## Implementation Decisions

- The publication unit remains `(service_unit_id, tenant_id, source_id)`. All Agents and workspaces belonging to one source pass or fail together; independent sources may publish separately.
- Prepare continues to parse service and tenant configuration needed to resolve identities and workspace locations. It also performs root/path and cross-tenant workspace ownership checks. It does not open `chats.json`, session bodies, dialog archives, or ledgers for semantic inventory.
- Prepare persists the resolved workspace map and structural discovery evidence in the manifest. It does not persist conversation-body inventory summaries, `chats_mtime_ns`, per-input digests, or identity evidence hashes.
- Prepare still checks the configured application schema and precreated target schema. It creates no business rows and does not publish sources.
- Migrate reads source publication rows before source file IO. A published source is skipped before its workspace inputs are opened.
- For each unpublished source, migrate performs path containment and no-follow checks, source byte and entry limits, per-file limits, chats registry validation, session identity/path mapping, session and ledger parsing, dialog/archive parsing, orphan and collision checks, message validation, and unsettled-turn checks while building bounded temporary workspace records.
- The bounded temporary records are completed for the source before the existing importer begins SQL and NAS writes. They live only for the current process and are removed after source processing. This preserves the existing scan-then-write importer contract and avoids broad changes to journal ordering, identity allocation, and partial-commit recovery.
- Migrate does not compare source mtimes or content digests with values from prepare. It also does not calculate checksums for its temporary inventory records. No manifest binding digest is calculated. Stability relies on the operational requirement that unpublished inputs, configuration evidence, and frozen identity mappings remain unchanged until publication.
- If migration fails while scanning, that source remains unpublished and independent sources continue. If a later SQL/NAS/write/verification failure occurs after import has begun, existing tickets and bundles remain the retry authority; published sources remain untouched.
- Target verification, transactional journal writes, uncertain-commit recovery, bundle durability, stable ticket identities, source failure isolation, and SQL-authoritative source publication remain unchanged.
- The jobs row stores a small `manifest-v1` source-binding marker instead of the full source binding. The manifest is the only persisted complete source mapping. Migrate copies its current form into the runtime output directory beside each per-service runtime reference.
- Runtime startup selects the unique tenant migration job for the service from SQL and obtains its NAS root from the target binding. It does not require a runtime mapping file or `SWE_CONVERSATION_SCOPE_MANIFEST`. Each source admission queries only that source's SQL publication proof. Deployments guarantee source workspace and configuration paths do not overlap, so runtime does not scan all source boundaries.
- The migration command does not generate runtime mapping files and does not require `--output-dir`; SQL is the sole record of source publication state.
- The deployment must install the same manifest for all instances of each migration and preserve it as read-only configuration. The existing guarantee of one migration process per application schema remains required.
- Historical shares remain excluded from migration input. Existing source publication and DBA finalization contracts remain unchanged.

## Testing Decisions

- The primary seam is an end-to-end prepare then migrate workflow against isolated MySQL and local source/NAS roots. Tests assert reports, SQL rows, source publication states, bundle availability, and retries rather than private helper calls.
- Prepare tests prove workspace identity and path mappings are frozen, schema preflight still runs, malformed conversation content is not parsed during prepare, and configuration/mapping failures are reported before migration.
- Migrate tests prove published sources are skipped before source file access, unpublished workspaces are scanned once, malformed/unsafe/oversized inputs fail only their source, healthy sources still publish, and target verification gates publication.
- Workflow tests prove there is no prepare-to-migrate mtime rejection and that the migration consumes the manifest mapping. The test does not mutate real inputs during a migration because operational immutability is a deployment precondition.
- Retry tests cover unchanged manifest/input continuation after a ticketed interruption, unknown commit recovery, and preservation of already-published sources.
- A scale test with many sources verifies `source_binding_text` stays bounded and the complete source mapping is kept in the manifest/runtime artifact.
- Runtime tests prove the installed runtime reference locates its colocated manifest, source publication remains SQL-authoritative, and in-place workspace boundaries use the manifest mapping.
- Existing tenant/source MySQL workflow tests, migration spool tests, journal tests, runtime admission tests, and migration lock-guard tests are prior art. MySQL fixture availability is required for the full workflow seam.

## Out of Scope

- Streaming each parsed chat/session directly to SQL before the source scan completes.
- Detecting source changes between prepare and migrate with mtimes, hashes, snapshots, or a second source inventory.
- Persisting parsed conversation bodies or durable semantic inventory records in the manifest or SQL.
- Changing the source publication unit, SQL ticket identity rules, or target verification contract.
- Introducing a new runtime environment variable, per-source distributed lock, or concurrent migration process support.
- Importing historical share records or changing DBA schema-finalization procedures.

## Further Notes

The operator must keep all old writers stopped and unpublished source inputs/configuration read-only and unchanged from prepare through publication. This is an operational prerequisite, not a property proven by migrate. The bounded temporary spool remains the seam between one source scan and the existing importer.
