## 1. Data Model And Store

- [x] 1.1 Add SQL migration for `swe_source_system_config` with `source_id`, `config_json`, `version`, `updated_by`, and `updated_at`
- [x] 1.2 Add source system config Pydantic models, default empty config, and JSON object validation
- [x] 1.3 Implement source system config store for get/upsert/delete/list operations by `source_id`
- [x] 1.4 Add store tests for missing rows, valid rows, invalid JSON/schema, version increment, arbitrary keys, and delete

## 2. Runtime Loading And Cache

- [x] 2.1 Implement source system config service with effective config resolution from defaults plus source override
- [x] 2.2 Add per-source in-process cache with TTL, version metadata, and last-known-good fallback behavior
- [x] 2.3 Bind effective source config to request state and context after source identity is resolved
- [x] 2.4 Add helper functions for `get_current_source_system_config` and context binding
- [x] 2.5 Add tests for default behavior, cache refresh, DB failure with cache, DB failure without cache, and context binding

## 3. Source Config APIs

- [x] 3.1 Add effective config read API using the current request `source_id`
- [x] 3.2 Add manager-only APIs to read, list, create, update, and delete source system config
- [x] 3.3 Ensure management APIs validate source identity, JSON object schema, and audit metadata
- [x] 3.4 Add API tests for authorized updates, delete, unauthorized rejection, effective reads, missing source defaults, and invalid config rejection

## 4. Console Integration

- [x] 4.1 Add Console API client and store for effective source system config
- [x] 4.2 Load effective source config on Console startup and refresh when active source changes
- [x] 4.3 Add Console tests for config loading and stale config prevention

## 5. Verification And Documentation

- [x] 5.1 Document the source system config table, default behavior, generic config shape, and failure behavior in analysis docs or playbook
- [x] 5.2 Run focused backend tests for source system config and existing source-scoped tenant tests
- [x] 5.3 Run focused Console tests for config loading
- [x] 5.4 Run `openspec status --change source-system-config` and confirm the change is apply-ready
