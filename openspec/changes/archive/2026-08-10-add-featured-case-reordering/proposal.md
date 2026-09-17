## Why

Featured cases expose a `sort_order` value but the management page cannot change it safely, and the current single-row update behavior can create duplicate or discontinuous positions. Management queries also mix current-branch and head-office cases, which makes independent ordering ambiguous once inline reordering is introduced.

## What Changes

- Add inline featured-case ordering with explicit edit, confirm, cancel, blur, validation, retry, cross-page navigation, and moved-row feedback states.
- Add an atomic reorder API that moves one case within its exact `source_id + bbk_id` queue and normalizes that queue to contiguous positions `1..N`.
- Keep enabled and disabled cases in the same ordering queue; visibility continues to be controlled separately by `is_active`.
- Preserve contiguous ordering when cases are created, reordered, or deleted, including repair of historical gaps and duplicate positions within the affected queue.
- Split management visibility into independently paginated current-branch and head-office scopes. Non-head-office contexts may inspect head-office cases in a separate read-only view, while only the head-office context may mutate that shared queue.
- Preserve runtime chat behavior: a non-head-office context displays current-branch cases first and then active head-office cases, with each source queue retaining its own relative order.
- Serialize concurrent mutations of the same queue so each request applies to the latest committed order and the later committed reorder determines the final requested position.

## Capabilities

### New Capabilities

- `featured-case-ordering`: Contiguous, dimension-scoped ordering semantics, atomic reorder behavior, validation, pagination relocation, and concurrent mutation rules.

### Modified Capabilities

- `cases-management`: The management page gains editable ordering and separate current-branch/head-office management scopes with read-only head-office access outside the head-office context.
- `cases-api`: Management list semantics become exact-scope queries, a dedicated reorder endpoint is added, and create/delete mutations preserve queue continuity while runtime display aggregation remains unchanged.

## Impact

- Frontend: featured-case management page, table columns, inline editing state, API types/hooks, pagination, scope tabs, error/success feedback, and UI tests.
- Backend: featured-case router, Pydantic request/response models, service and store ordering operations, transactional locking, exact-scope management queries, mutation authorization, and unit/API tests.
- Database: no schema change is expected; existing `swe_featured_case.sort_order` and `(source_id, bbk_id)` index are reused.
- Runtime display: chat query composition remains current branch first plus head-office fallback, but it consumes normalized per-scope ordering.
- Documentation: OpenSpec deltas define the new ordering contract; `console/DESIGN.md` does not require a reusable-rule update unless implementation review introduces a broader inline-table-editing rule.
