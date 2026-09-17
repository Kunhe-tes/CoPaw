# File Manager Bounded Paths and JSON Listing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound File Manager upload and large-preview I/O, then make directory and JSON recycle listings page from stable process-local snapshots without SQLite/WAL.

**Architecture:** Keep descriptor-safe filesystem access and the archive `index.json` transition protocol intact. Add synchronous stream publication beside the existing byte upload method, use it from the mutation worker lane, and add a bounded snapshot cache owned by `file_manager.py` and shared by per-request service instances. Signed cursors bind a snapshot token and fail with `FileManagerConflictError` when the snapshot is unavailable or stale.

**Tech Stack:** Python 3.10+, FastAPI/Starlette `UploadFile`, AnyIO worker lanes, stdlib `OrderedDict`, descriptor I/O, pytest, GitNexus.

---

## File map

| File | Responsibility |
| --- | --- |
| `src/swe/app/file_manager.py` | Stream publication, bounded large-file snapshots, cache/snapshot cursor lifecycle, JSON recycle pagination and mutation invalidation. |
| `src/swe/app/routers/console.py` | Pass `UploadFile.file` into the existing mutation worker rather than reading a complete body. |
| `tests/unit/app/test_file_manager.py` | File-service tests for chunks, preview bounds, snapshot reuse/invalidation, and recycle pagination. |
| `tests/unit/routers/test_console_chat_stream.py` | HTTP upload regression proving the route does not call `UploadFile.read`. |

## Task 1: Stream File Manager uploads through the secure publication path

**Files:**
- Modify: `src/swe/app/file_manager.py:681-750`
- Modify: `src/swe/app/routers/console.py:1159-1213`
- Modify: `tests/unit/app/test_file_manager.py`
- Modify: `tests/unit/routers/test_console_chat_stream.py`

- [ ] **Step 1: Run GitNexus impact before changing the existing upload method and route.**

  Run upstream impact on `FileManagerService.upload_bytes` and `post_file_manager_upload`; inspect all direct callers. Stop for review if either is HIGH or CRITICAL.

- [ ] **Step 2: Write failing service tests for chunking and cleanup.**

  Add a `BytesIO` subclass that records `read(size)` arguments and rejects an unbounded read. Assert `upload_stream` writes a 10 MiB payload byte-for-byte, every source read is `_FILE_READ_CHUNK_BYTES`, and all requested sizes are bounded. Add an over-limit source and assert the service raises `FileManagerPathError`, the destination is absent, and no `.<name>.file-manager-*` entry remains.

  ```python
  class RecordingSource(io.BytesIO):
      def __init__(self, data: bytes) -> None:
          super().__init__(data)
          self.read_sizes: list[int] = []

      def read(self, size: int = -1) -> bytes:
          assert size > 0
          self.read_sizes.append(size)
          return super().read(size)

  source = RecordingSource(b"x" * (10 * 1024 * 1024))
  item = service.upload_stream("upload", "", "large.bin", source)
  assert (tmp_path / "media" / item.name).read_bytes() == b"x" * len(source.getvalue())
  assert set(source.read_sizes) == {_FILE_READ_CHUNK_BYTES}
  ```

- [ ] **Step 3: Run the new tests and confirm they fail because `upload_stream` does not exist.**

  Run:

  ```bash
  ../../venv/bin/python -m pytest tests/unit/app/test_file_manager.py -k 'upload_stream' -v
  ```

  Expected: collection/import failure or attribute error.

- [ ] **Step 4: Refactor publication into one source-reader implementation.**

  Add a synchronous `upload_stream(root, directory_path, filename, source: BinaryIO) -> FileManagerItem` method. It uses the same validation, no-follow directory fd, exclusive temporary file, link publication, `fsync`, collision mapping, and `finally` cleanup as `upload_bytes`. Replace the direct `_write_all` call with a loop that reads `_FILE_READ_CHUNK_BYTES`, increments `copied`, rejects when `copied > MAX_UPLOAD_BYTES`, and writes each chunk. Make `upload_bytes` delegate through `io.BytesIO(content)` so its existing API retains exactly the same result and errors.

  ```python
  copied = 0
  while chunk := source.read(_FILE_READ_CHUNK_BYTES):
      copied += len(chunk)
      if copied > MAX_UPLOAD_BYTES:
          raise FileManagerPathError("File too large (max 10 MB)")
      _write_all(temporary_fd, chunk)
  ```

- [ ] **Step 5: Convert only the File Manager route to source streaming.**

  Remove `await file.read(MAX_UPLOAD_BYTES + 1)`. Resolve the workspace and call:

  ```python
  item = await run_file_manager_mutation(
      service.upload_stream, root, path, filename, file.file,
  )
  ```

  Keep the existing success/failure audit calls and public 400 mapping. Do not modify the unrelated `/console/upload` endpoint in this plan.

- [ ] **Step 6: Add the route regression and run tests.**

  Patch the route fixture with an `UploadFile` whose async `read` raises `AssertionError`; POST a multipart File Manager upload and assert 200 plus the published bytes. Run:

  ```bash
  ../../venv/bin/python -m pytest \
    tests/unit/app/test_file_manager.py -k 'upload_stream or upload_rejects' \
    tests/unit/routers/test_console_chat_stream.py -k 'file_manager_upload' -v
  ```

- [ ] **Step 7: Commit the streaming upload change.**

  ```bash
  git add src/swe/app/file_manager.py src/swe/app/routers/console.py \
    tests/unit/app/test_file_manager.py tests/unit/routers/test_console_chat_stream.py
  git commit -m "perf(file-manager): stream controlled uploads"
  ```

## Task 2: Bound large-file preview classification

**Files:**
- Modify: `src/swe/app/file_manager.py:471-559`
- Modify: `tests/unit/app/test_file_manager.py`

- [ ] **Step 1: Run GitNexus impact on `read_file_snapshot` and `read_text_preview`.**

  Record direct callers and risk before editing; review a HIGH/CRITICAL result before proceeding.

- [ ] **Step 2: Write failing bounded-read tests.**

  Monkeypatch `os.read` only for a known opened descriptor, record byte counts, and read a `(TEXT_PREVIEW_LIMIT_BYTES + 64 KiB)` text file. Assert the total is no more than `TEXT_PREVIEW_LIMIT_BYTES + 4`, `is_truncated is True`, `editable is False`, and the response does not call `hashlib.sha256` over the whole file. Add a second test with a multibyte UTF-8 character crossing the preview boundary and assert the returned preview is valid UTF-8.

- [ ] **Step 3: Run the selected tests and verify the current full scan fails the read bound.**

  ```bash
  ../../venv/bin/python -m pytest tests/unit/app/test_file_manager.py -k 'large_preview' -v
  ```

- [ ] **Step 4: Split small and large snapshot paths.**

  In `read_file_snapshot`, fstat first. For sizes at or below `TEXT_PREVIEW_LIMIT_BYTES`, retain the existing full digest and decoder loop. For larger files, read a maximum sample of `TEXT_PREVIEW_LIMIT_BYTES + 4`, use `_decode_text_sample(..., sample_is_truncated=True)`, check the descriptor identity afterward, and set the read-only revision from `st_dev`, `st_ino`, `st_size`, and `st_mtime_ns` with an explicit `stat:` prefix. Never pass this revision to `save_text`, because `is_truncated` already makes it non-editable.

- [ ] **Step 5: Run service regressions and commit.**

  ```bash
  ../../venv/bin/python -m pytest tests/unit/app/test_file_manager.py -k 'preview or save_text' -v
  git add src/swe/app/file_manager.py tests/unit/app/test_file_manager.py
  git commit -m "perf(file-manager): bound large preview reads"
  ```

## Task 3: Add bounded snapshots and snapshot-aware cursors

**Files:**
- Modify: `src/swe/app/file_manager.py:90-110,362-428,1724-2052`
- Modify: `tests/unit/app/test_file_manager.py`

- [ ] **Step 1: Run GitNexus impact on `list_directory`, `_directory_candidates`, `_validate_cursor_context`, and `_encode_cursor`.**

  Report direct callers and inspect HIGH/CRITICAL paths before editing.

- [ ] **Step 2: Write failing directory snapshot tests.**

  Create 102 entries, request page one then page two, and spy on `_directory_candidates`; assert it runs once. Change the directory between pages and assert the old cursor raises `FileManagerConflictError`. Add an eviction test by lowering a module-private cache capacity in the fixture, then assert an evicted cursor raises the same conflict rather than returning a different page.

- [ ] **Step 3: Run tests and verify repeated scan / old cursor behavior fails.**

  ```bash
  ../../venv/bin/python -m pytest tests/unit/app/test_file_manager.py -k 'directory_snapshot' -v
  ```

- [ ] **Step 4: Implement a module-private bounded snapshot cache.**

  Define frozen snapshot/key records, an `OrderedDict` cache guarded by a lock, TTL, global capacity, and per-workspace quota. A snapshot stores generated `FileManagerItem` values, a random version token, and an identity probe. Use `(workspace_dir, root, normalized_path, normalized_query)` as the key. The first page builds it from descriptor-safe enumeration; later pages use it only after a cheap directory `fstat` identity/mtime probe matches. Cache misses, expiry, eviction, and probe mismatch invalidate the snapshot.

- [ ] **Step 5: Version signed cursors and return a restartable conflict.**

  Add `snapshot` to the signed v3 cursor payload. `_validate_cursor_context` returns its snapshot token with the last item. A valid v2 cursor remains readable only for the first-page compatibility path; any v2 follow-up causes `FileManagerConflictError("Directory listing changed; refresh and retry")`. Existing malformed/tampered cursors remain `FileManagerPathError` and map to 403.

- [ ] **Step 6: Invalidate after successful workspace mutations.**

  Add a cache invalidation helper keyed by workspace/root/parent path. Call it after successful save, streamed/byte upload, archive, restore, and purge publication. Invalidate both exact parent snapshots and the recycle root when archive state changes. Do not invalidate on a rejected mutation.

- [ ] **Step 7: Run snapshots tests and commit.**

  ```bash
  ../../venv/bin/python -m pytest tests/unit/app/test_file_manager.py -k 'directory_snapshot or cursor' -v
  git add src/swe/app/file_manager.py tests/unit/app/test_file_manager.py
  git commit -m "perf(file-manager): cache stable directory pages"
  ```

## Task 4: Page JSON recycle metadata from the same snapshot cache

**Files:**
- Modify: `src/swe/app/file_manager.py:362-428,1138-1181`
- Modify: `tests/unit/app/test_file_manager.py`
- Modify: `tests/unit/routers/test_console_chat_stream.py`

- [ ] **Step 1: Run GitNexus impact on `_list_recycle_items`, `archive_file`, `restore_recycle_item`, and `purge_recycle_item`.**

  Inspect direct callers and warn before changing any HIGH/CRITICAL result.

- [ ] **Step 2: Write failing recycle pagination and invalidation tests.**

  Seed 102 valid index records, request the first and second recycle pages, and spy on `_load_recovered_archive_index`; assert one load. Assert the second page cursor is accepted, pages do not overlap, and an archive/restore/purge invalidates the first cursor with `FileManagerConflictError`. Add HTTP coverage that `root=recycle` accepts a cursor but rejects a non-empty path or query.

- [ ] **Step 3: Run tests and confirm recycle currently rejects cursors.**

  ```bash
  ../../venv/bin/python -m pytest \
    tests/unit/app/test_file_manager.py -k 'recycle_pagination' \
    tests/unit/routers/test_console_chat_stream.py -k 'recycle' -v
  ```

- [ ] **Step 4: Build and serve recycle snapshots without changing JSON durability.**

  Permit a cursor for `FileManagerRoot.RECYCLE` and build a snapshot from `_load_recovered_archive_index()` only on the first page. Sort exactly by current archived timestamp/id ordering, page at `FILE_MANAGER_PAGE_SIZE`, and encode the snapshot-aware cursor. Validate archive-index identity by opening/fstat'ing `governance/archive/index.json`; a missing or changed identity invalidates the snapshot and raises the restartable conflict. Do not alter `_save_archive_index`, recovery transitions, or archive payload storage.

- [ ] **Step 5: Run tests and commit.**

  ```bash
  ../../venv/bin/python -m pytest \
    tests/unit/app/test_file_manager.py -k 'recycle or archive' \
    tests/unit/routers/test_console_chat_stream.py -k 'file_manager_recycle' -v
  git add src/swe/app/file_manager.py tests/unit/app/test_file_manager.py \
    tests/unit/routers/test_console_chat_stream.py
  git commit -m "perf(file-manager): page cached json recycle listings"
  ```

## Task 5: Regression, format, and GitNexus review

- [ ] **Step 1: Run all relevant tests.**

  ```bash
  ../../venv/bin/python -m pytest \
    tests/unit/app/test_file_manager.py \
    tests/unit/app/test_file_manager_execution.py \
    tests/unit/routers/test_console_chat_stream.py \
    tests/unit/routers/test_agents_tenant_scope.py -q
  ```

- [ ] **Step 2: Validate formatting with the project hook.**

  ```bash
  pre-commit run black --files \
    src/swe/app/file_manager.py src/swe/app/routers/console.py \
    tests/unit/app/test_file_manager.py tests/unit/routers/test_console_chat_stream.py
  ```

- [ ] **Step 3: Run GitNexus before the final handoff.**

  ```text
  detect_changes({
    repo: "CoPaw",
    scope: "compare",
    base_ref: "797450d88",
    worktree: "/Users/shixiangyi/code/Swe/.worktrees/file-manager-runtime-performance"
  })
  ```

  Review all direct callers if the result is HIGH or CRITICAL. Confirm no database, `.sqlite`, `-wal`, migration, or archive-protocol files were added.

## Plan self-review

- **Spec coverage:** Tasks 1 and 2 cover both bounded data paths; Tasks 3 and 4 cover ordinary and JSON recycle snapshots, stable cursors, eviction, invalidation, and pagination; Task 5 covers regressions and explicitly checks the no-SQLite scope.
- **Placeholder scan:** No implementation step defers error handling or test behavior.
- **Type consistency:** Route upload invokes the proposed synchronous `upload_stream`; cache cursors use the existing `FileManagerConflictError` HTTP 409 mapping; all filesystem work remains inside the existing worker lanes.
