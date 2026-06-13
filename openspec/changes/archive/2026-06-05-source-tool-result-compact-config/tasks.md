## 1. Backend Source Config Registry

- [x] 1.1 Extend the source system config registry to support typed registered settings beyond boolean switches.
- [x] 1.2 Register `tool_result_compact.enabled`, `recent_n`, `old_max_bytes`, `recent_max_bytes`, and `retention_days` with defaults and validation ranges.
- [x] 1.3 Update default payload generation, normalization, and default override pruning to handle the new typed settings while preserving existing switch behavior.
- [x] 1.4 Add unit tests for valid tool result config, invalid values, partial overrides, and default-equivalent pruning.

## 2. Runtime Resolution

- [x] 2.1 Add a helper that resolves effective tool result compaction config from Agent runtime config plus current source system config.
- [x] 2.2 Ensure missing source fields inherit from Agent runtime config instead of source registered defaults.
- [x] 2.3 Add unit tests for no override, partial override, full override, and disabled compaction cases.

## 3. Backend Runtime Integration

- [x] 3.1 Update `MemoryCompactionHook` to use the resolved tool result compaction config before calling `compact_tool_result`.
- [x] 3.2 Update `SWEAgent.reply()` to set `current_recent_max_bytes` from the resolved config.
- [x] 3.3 Update `summary_memory()` and `dream_memory()` recent max bytes binding to use the same resolved config.
- [x] 3.4 Add focused regression tests proving source `recent_max_bytes` affects read-file truncation context and source `enabled=false` skips compaction.

## 4. Console System Config Page

- [x] 4.1 Extend the SystemConfigPage registry/types to support typed numeric config definitions or a dedicated tool result compact definition.
- [x] 4.2 Add a tool result compaction card to `system-config-page` with controls for enabled, recent count, old max bytes, recent max bytes, and retention days.
- [x] 4.3 Preserve unknown raw source config keys when editing tool result compaction values.
- [x] 4.4 Add frontend validation for numeric ranges and `recent_max_bytes >= old_max_bytes`.
- [x] 4.5 Refresh effective source config after saving or deleting current source config.

## 5. Verification

- [x] 5.1 Run targeted backend tests for source system config and tool result compaction resolution.
- [x] 5.2 Run targeted Console tests for SystemConfigPage.
- [x] 5.3 Run `openspec status --change source-tool-result-compact-config` and confirm all proposal artifacts are complete.
