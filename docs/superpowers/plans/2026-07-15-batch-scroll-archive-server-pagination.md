# Batch Scroll And Archive Server Pagination

## Scope

- Keep the existing Monitor batch API, archive API routes, permissions, and response shapes unchanged.
- Make the `所有 Batch` list the independently scrollable region inside its fixed-height pane while keeping the filter, column header, and pagination visible.
- Make the scroll region keyboard focusable and named for assistive technology.
- Replace the archive table's client-only pagination over the first 100 rows with controlled server pagination using `page`, `page_size`, and response `total`.
- Keep protected-file and cleanup-audit behavior unchanged.
- Preserve the existing Worker adjustment carousel and cron synchronization changes already present in the worktree.

## Implementation Steps

1. Extend the Cron batch-dispatch test with an accessible scroll-region contract and confirm it fails before the markup change.
2. Add a focused `ArchiveGovernance` regression test proving the first request uses page 1/page size 10 and page navigation requests page 2 from the server.
3. Harden the `Spin`/flex height chain and make the Batch list the sole vertical scroll owner.
4. Add controlled archive page, page-size, and total state; wire Ant Design Table pagination to the archive API.
5. Run focused Vitest files, Prettier, TypeScript/build checks, frontend quality review, and GitNexus change detection.

## Verification

- Red: the Batch list has no named focusable scroll region, and archive loading requests only `page_size=100` without a page.
- Green: Batch rows scroll inside the pane with pagination fixed below; archive page 2 triggers `/archive/items?page=2&page_size=10` and uses the backend `total`.
- `cd console; .\node_modules\.bin\vitest.cmd run src/pages/Monitor/CronBatchDispatch/index.test.tsx src/pages/Harness/ContinuousIteration/components/ArchiveGovernance.test.tsx`
- `cd console; .\node_modules\.bin\prettier.cmd --check src/pages/Monitor/CronBatchDispatch/index.tsx src/pages/Monitor/CronBatchDispatch/index.module.less src/pages/Monitor/CronBatchDispatch/index.test.tsx src/pages/Harness/ContinuousIteration/components/ArchiveGovernance.tsx src/pages/Harness/ContinuousIteration/components/ArchiveGovernance.test.tsx`
- `cd console; npm run build`
- GitNexus `detect_changes` for the final uncommitted diff.
