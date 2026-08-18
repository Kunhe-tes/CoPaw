## Context

Featured cases are persisted in `swe_featured_case` and served through separate runtime-display and administration routes under `/api/featured-cases`. The runtime query currently aggregates cases by request context, while the management query also mixes the current branch with head-office cases. Creation assigns `MAX(sort_order) + 1`, generic updates change only one row, and deletion does not close gaps. The management table is paginated and displays `sort_order`, but it has no editing interaction.

Ordering becomes a multi-row consistency operation once administrators can move a case to an arbitrary position. The operation must preserve branch isolation, head-office sharing, pagination, and concurrent edits without exposing duplicate or discontinuous positions. Existing `bbk_id` values may represent head office as `NULL`, an empty string, or `"100"`; the new ordering behavior must treat these as one logical scope while converging writes on `"100"`.

The relevant stakeholders are branch operators managing their own featured cases, head-office operators managing shared cases, and chat users who receive branch-first plus head-office fallback content.

## Goals / Non-Goals

**Goals:**

- Maintain one contiguous `1..N` queue for every logical `source_id + bbk_id` scope.
- Provide atomic create, reorder, and delete behavior that serializes concurrent mutations of the same queue.
- Add compact, keyboard-accessible inline ordering to the management table with recoverable failures.
- Separate exact-scope management pagination from runtime aggregation.
- Keep head-office cases visible but read-only to non-head-office contexts.
- Preserve chat ordering as active branch cases followed by active head-office cases.

**Non-Goals:**

- Drag-and-drop ordering.
- Cross-branch or cross-source moves.
- A global ordering sequence shared by branch and head-office cases.
- Reordering only the currently visible page.
- Changing featured-case content fields, chat-card presentation, or the meaning of `is_active`.
- Introducing a new database table or ordering column.

## Decisions

### 1. Ordering is scoped by canonical `source_id + bbk_id`

Every case belongs to exactly one logical ordering queue. Branch IDs are exact scopes. Missing, blank, and `"100"` BBK values identify the head-office scope and are canonicalized to `"100"` for new writes. Legacy head-office rows with `NULL` or blank BBK values participate in the same queue and are normalized when that queue is mutated.

Enabled and disabled cases share the queue. Runtime display filters inactive rows but preserves the relative order of the remaining active rows.

Alternative considered: order the management result after merging branch and head-office cases. This was rejected because the runtime query deliberately groups branch cases before shared cases, so a single numeric sequence would be misleading and would couple unrelated administrators.

### 2. Management lists use exact scopes; runtime lists aggregate scopes

`GET /api/featured-cases/admin/cases` continues to accept `bbk_id`, but administration interprets it as an exact logical scope. The branch tab requests the current branch ID; the head-office tab requests `100`. Each tab has an independent count and pagination sequence ordered by `sort_order ASC, id ASC`.

The runtime `GET /api/featured-cases` behavior remains separate:

- a head-office request returns active head-office cases only;
- a branch request returns active exact-branch cases first and active head-office cases second;
- each section uses its own contiguous order.

Non-head-office contexts may read the head-office management tab but receive no mutation controls. Backend mutation authorization also verifies that the requested case scope equals the caller's normalized `X-Bbk-Id`, so the read-only rule is not merely cosmetic.

Alternative considered: hide head-office cases from branch management entirely. This was rejected because branch operators need to understand the shared cases that will appear in chat.

### 3. Reordering uses a dedicated endpoint

Add:

```http
PUT /api/featured-cases/admin/cases/{case_id}/order
Content-Type: application/json

{"sort_order": 2}
```

The request model requires an integer greater than or equal to 1. Values above the queue length are clamped to the queue length. Empty, non-numeric, fractional, zero, and negative values are rejected without mutation.

The response is:

```json
{
  "success": true,
  "data": {
    "case_id": 42,
    "sort_order": 2,
    "total": 37
  }
}
```

The dedicated route makes it explicit that one request updates a queue rather than a single record. Generic case updates no longer serve as the ordering contract.

Alternative considered: reuse `PUT /admin/cases/{case_id}` with `sort_order`. This was rejected because generic partial updates do not communicate multi-row locking, normalization, pagination relocation, or scope authorization.

### 4. Queue mutations are transactional and stable

Create, reorder, and delete acquire one database connection and transaction for the complete logical queue mutation. The store selects the affected indexed queue with `FOR UPDATE`, ordered by `sort_order ASC, id ASC`. The stable `id` fallback resolves historical duplicate positions deterministically.

For reorder, the store removes the target ID from the locked ordered ID list, inserts it at the clamped zero-based destination, and writes positions `1..N` for the entire queue before commit. For delete, it removes the target and renumbers survivors. For create, it locks the queue, normalizes existing rows, and appends the new row at `N + 1`. Any failure rolls back the complete mutation.

The compound `(source_id, bbk_id)` index remains the queue lookup path. Head-office compatibility predicates include legacy null/blank values; once that queue is mutated, affected legacy rows are persisted with canonical `bbk_id="100"`.

Concurrent requests for the same queue serialize on the locked index range. Each request operates on the latest committed ordering; the later committed reorder therefore determines its target case's final requested position. Different branch queues remain independent.

Alternative considered: update only the numeric range between old and new positions. Full queue normalization was selected because it also repairs historical gaps and duplicates, has deterministic behavior, and featured-case administration is a low-frequency operation. Tests and metrics should still cover a realistically large queue.

### 5. Inline editing is server-confirmed and recoverable

The sort column displays the number plus a permanently discoverable edit icon for writable rows. Only one row enters edit mode at a time. Edit mode uses a compact integer `InputNumber`, an accessible confirm action, and a cancel action without changing table row height.

- Initial value is selected automatically.
- Enter, confirm, or blur commits a changed valid value through a single guarded submission path.
- Escape cancels and restores the last server value.
- An unchanged value exits without a request.
- During submission, the input and competing sort actions are disabled.
- Failure keeps the input value and edit state, displays an inline error plus a message, and permits retry or Escape cancellation.
- Success computes `ceil(final_sort_order / page_size)`, loads that exact-scope page from the server, and briefly highlights the moved row while also showing success feedback.

The head-office tab omits edit controls in non-head-office contexts and displays a concise read-only explanation. A head-office context shows only its head-office scope rather than redundant tabs.

Alternative considered: optimistic local row movement. This was rejected because cross-page moves and concurrent mutations require the server to be authoritative.

## Risks / Trade-offs

- **[Full-queue writes grow with queue size]** → Featured-case mutations are low frequency; use indexed row locking, batch updates on one connection, and add a representative large-queue test. Revisit range updates only if measured latency warrants it.
- **[Autocommit connection helpers can accidentally split the transaction]** → Keep all reads and writes for one mutation on the explicitly acquired connection and test rollback behavior; do not call helpers that acquire separate pooled connections inside the transaction.
- **[Blur and confirm can fire duplicate submissions]** → Route all commit triggers through one guarded handler and suppress duplicate submission while saving.
- **[A moved row may leave the current page]** → Use the server-returned final position to navigate to the destination page, reload, and highlight the case.
- **[Legacy head-office BBK representations can form multiple queues]** → Treat null, blank, and `100` as one logical queue and canonicalize them transactionally on the first mutation.
- **[Frontend-only read-only controls are bypassable]** → Enforce source and BBK scope authorization in every management mutation route.
- **[Runtime behavior could regress while management queries change]** → Keep separate store methods and explicit tests for head-office-only runtime display and branch-first head-office fallback.

## Migration Plan

1. Add request/response models, exact-scope query helpers, transactional queue mutation methods, and authorization checks behind the existing API prefix.
2. Add the dedicated reorder endpoint and update create/delete to preserve queue continuity.
3. Add frontend API types/hooks, exact-scope tabs, inline editing, page relocation, and error states.
4. Deploy without a schema migration. Legacy queue gaps and head-office BBK variants are repaired lazily when their queue is first created in, reordered, or deleted from.
5. Verify backend unit/API tests, frontend component tests, lint/type/build checks, runtime branch/head-office display paths, and the management UI at required desktop and embedded sizes.

Rollback removes the new frontend controls and endpoint while retaining normalized `sort_order` and canonical head-office BBK values; those data changes are compatible with the prior ascending-order queries.

## Open Questions

None. Product behavior, failure handling, pagination, scope separation, active-state participation, deletion compaction, and concurrency semantics were confirmed during exploration.
