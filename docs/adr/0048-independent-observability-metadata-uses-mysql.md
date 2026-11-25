---
status: accepted
---

# Independent Observability Metadata Uses MySQL

On 2026-11-15 the user selected independent MySQL tables and indexes, accessed through independent connection configuration, for the new Agent observability metadata. No ES/OpenSearch is added, and no legacy observability table, schema, or query is reused. This keeps the structured metadata and derived query views in one selected store while leaving log collection and insertion operations with the user under ADR 0047. General database infrastructure may be used without depending on legacy observability logic.

The user explicitly deferred data cleanup: this release does not add a retention TTL, scheduled deletion, automatic archival, or partition-expiration task. This replaces the unaccepted 30-day proposal; it is not an assurance of unlimited capacity. NAS body ownership, authorization, deletion and visibility remain governed by the conversation domain, regardless of how long observability metadata remains in MySQL.

The project owns the event schema, MySQL DDL/indexes, deterministic idempotent projection, query APIs and Console views. The user inserts metadata events; they are not required to implement a second derived-state processor. Actual MySQL compatibility, ingestion contract and query capacity are verified separately; deployment-side log collection is outside project scope.
