## 1. Impact Analysis and Test Baseline

- [x] 1.1 Run GitNexus upstream impact analysis for every scanner, lifecycle, router, hook, and Console symbol that will be edited; report and resolve any HIGH or CRITICAL blast radius before implementation.
- [x] 1.2 Add or update focused backend and frontend tests that capture the database-only, paginated response, stable-ID deletion, unavailable-store, and bounded Console loading contracts before changing implementation.

## 2. Database History Store

- [x] 2.1 Add the skill scan history record/page models and an async MySQL-compatible store with idempotent table/index initialization.
- [x] 2.2 Implement insert, count plus bounded newest-first page query, delete-by-stable-ID, and clear-all operations, including findings serialization and store-unavailable errors.
- [x] 2.3 Add focused store tests for field round-tripping, deterministic ordering, page boundaries, totals, deletion, clearing, and database failures.

## 3. Non-Blocking Scanner Recording

- [x] 3.1 Add an application-scoped bounded recorder that accepts records synchronously from the app loop or worker threads and persists them asynchronously through the history store.
- [x] 3.2 Initialize the store and recorder in the FastAPI lifespan, install the recorder into the scanner, and drain it before database shutdown.
- [x] 3.3 Replace all SWE scanner JSON history reads and writes with recorder submission, remove JSON history APIs, and preserve block/warn behavior when submission or persistence fails.
- [x] 3.4 Add scanner/recorder tests for app-loop and worker-thread submission, graceful draining, queue/write failures, absent recorder behavior, and confirmation that legacy JSON is never accessed.

## 4. Paginated History API

- [x] 4.1 Define the paginated history response and stable record-ID API models.
- [x] 4.2 Change the history list route to validated `page`/`page_size` database queries with defaults 1/20, minimum page size 10, and maximum 100, returning explicit 503 when the store is unavailable.
- [x] 4.3 Change single deletion from array index to stable database ID and route clear-all through the store, preserving 404 and adding unavailable-store handling.
- [x] 4.4 Add router tests for pagination validation and response shape, newest-first pages, page overflow, stable-ID delete, clear-all, 404, and 503 behavior.

## 5. Console Integration

- [x] 5.1 Update the Security API client and types for the paginated response, page parameters, stable history IDs, and delete-by-ID requests.
- [x] 5.2 Replace local history slicing with controlled server pagination, bounded refetches, page-size reset, and page correction after deletion or clear-all while leaving whitelist behavior unchanged.
- [x] 5.3 Add a history-scoped unavailable/error state that leaves the Skill Scanner tab and other Security controls interactive.
- [x] 5.4 Add focused Console tests proving only the active page is requested/rendered and pagination/deletion/error interactions remain responsive.

## 6. Verification

- [x] 6.1 Run focused backend tests plus relevant lint/type checks for scanner history, lifecycle initialization, and config routes.
- [x] 6.2 Run focused frontend tests, formatting/lint/type checks, and a production Console build.
- [x] 6.3 Exercise the Security page with a large database history to verify bounded response/rendering, pagination totals, stable deletion, clear-all, tab switching, and database-unavailable behavior.
- [x] 6.4 Run GitNexus `detect_changes()` against `main` and confirm only the expected scanner-history execution flows and symbols are affected.

## 7. Review Remediation

- [x] 7.1 Make worker-thread submissions reserve bounded capacity before acknowledgement, make flush/stop wait for all accepted outstanding work, stop scan producers before recorder shutdown, and add deterministic race regression tests.
- [x] 7.2 Add a database-backed latest-warning-by-skill query and bounded API contract, update all install/import/broadcast warning consumers, and cover batches larger than one history page.
- [x] 7.3 Add latest-request-wins history loading and automatic correction for pages invalidated by concurrent deletion, preserving the paginator for non-zero totals.
- [x] 7.4 Add visible pending and failure feedback for single-delete, allow-and-remove, and clear-all history mutations.
- [x] 7.5 Run focused and adjacent backend/frontend tests, formatting, lint, type checks, production build, strict OpenSpec validation, and GitNexus change detection.

## 8. P2 Follow-up Remediation

- [x] 8.1 Change recorder flushes to a captured accepted-work fence, add bounded route and graceful-shutdown timeouts, and cover later submissions plus stalled writes with deterministic tests.
- [x] 8.2 Add a server-issued warning cursor, filter latest-warning queries to the current operation window, update every install/import/save/broadcast consumer, and test that historical warnings are suppressed.
- [x] 8.3 Run focused and adjacent backend/frontend verification, strict OpenSpec validation, and GitNexus change detection against `main`.
