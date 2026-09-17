# Recycle Listing Complexity Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `_list_recycle_items` cognitive complexity to 15 or lower while preserving recycle-listing and cursor behaviour.

**Architecture:** Keep the method as orchestration and extract index identity, row conversion, and snapshot pagination helpers. Initial and cursor requests use one paging implementation.

**Tech Stack:** Python, Pydantic, pytest, GitNexus.

---

### Task 1: Characterize preserved behaviour

**Files:**

- Modify: `tests/unit/app/test_file_manager.py`

- [ ] **Step 1: Write a malformed-row test**

```python
def test_recycle_listing_skips_malformed_archive_index_rows(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    archive_dir = tmp_path / "governance" / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "index.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "valid-item",
                        "original_path": "reports/valid.txt",
                        "archived_at": "2026-07-30T00:00:00+00:00",
                        "size_bytes": 12,
                    },
                    {"id": "", "original_path": "bad.txt"},
                    "not-a-record",
                ],
            },
        ),
        encoding="utf-8",
    )

    listing = service.list_directory("recycle")

    assert [item.archive_item_id for item in listing.items] == ["valid-item"]
```

- [ ] **Step 2: Verify the characterization**

Run: `venv/bin/python -m pytest tests/unit/app/test_file_manager.py::test_recycle_listing_skips_malformed_archive_index_rows -q`

Expected: PASS before refactoring; malformed records remain hidden.

- [ ] **Step 3: Write a multi-page listing test**

```python
def test_recycle_listing_pages_through_a_stable_snapshot(tmp_path: Path) -> None:
    service = _service(tmp_path)
    archive_dir = tmp_path / "governance" / "archive"
    archive_dir.mkdir(parents=True)
    rows = [
        {
            "id": f"item-{index:03d}",
            "original_path": f"reports/{index:03d}.txt",
            "archived_at": (
                f"2026-07-30T00:{index // 60:02d}:{index % 60:02d}+00:00"
            ),
            "size_bytes": index,
        }
        for index in range(file_manager.FILE_MANAGER_PAGE_SIZE + 1)
    ]
    (archive_dir / "index.json").write_text(
        json.dumps({"items": rows}), encoding="utf-8"
    )

    first = service.list_directory("recycle")
    second = service.list_directory("recycle", cursor=first.next_cursor)

    assert len(first.items) == file_manager.FILE_MANAGER_PAGE_SIZE
    assert first.next_cursor is not None
    assert second.next_cursor is None
    assert {item.archive_item_id for item in [*first.items, *second.items]} == {
        row["id"] for row in rows
    }
```

- [ ] **Step 4: Verify paging characterization**

Run: `venv/bin/python -m pytest tests/unit/app/test_file_manager.py::test_recycle_listing_pages_through_a_stable_snapshot -q`

Expected: PASS before refactoring; the second page completes the stable snapshot.

### Task 2: Extract focused recycle-listing helpers

**Files:**

- Modify: `src/swe/app/file_manager.py:FileManagerService._list_recycle_items`
- Modify: `tests/unit/app/test_file_manager.py`

- [ ] **Step 1: Re-run impact analysis immediately before changing the method**

Run GitNexus: `impact({target: "_list_recycle_items", direction: "upstream", repo: "CoPaw"})`.

Expected: direct caller `list_directory`, indirect console route, no HIGH or CRITICAL risk.

- [ ] **Step 2: Add index-identity and row-conversion helpers**

```python
def _recycle_index_identity(self) -> tuple[int, int, int]:
    index_path = self._workspace_dir / "governance" / "archive" / "index.json"
    try:
        index_stat = index_path.stat()
    except FileNotFoundError:
        return (0, 0, 0)
    return (index_stat.st_dev, index_stat.st_ino, index_stat.st_mtime_ns)

def _recycle_listing_item(self, record: object) -> FileManagerItem | None:
    if not isinstance(record, dict):
        return None
    try:
        archive_item_id = self._validate_archive_item_id(
            str(record.get("id") or ""),
        )
        original_path = self._validate_archive_original_path(record)
        archived_at = _parse_archive_datetime(record.get("archived_at"))
        size_bytes = int(record.get("size_bytes") or 0)
    except (TypeError, ValueError, FileManagerPathError):
        return None
    return FileManagerItem(
        name=original_path.rsplit("/", maxsplit=1)[-1],
        path=original_path,
        kind=FileManagerItemKind.FILE,
        size_bytes=max(0, size_bytes),
        modified_at=archived_at,
        capabilities=FileManagerCapabilities(),
        archive_item_id=archive_item_id,
        original_path=original_path,
        archived_at=archived_at,
    )
```

- [ ] **Step 3: Add a shared snapshot-page helper**

The helper accepts the cache key, index identity, validated cursor state, and optional initial items. It preserves all existing conflict cases: a missing snapshot version, expired/changed snapshot, or missing cursor anchor raises `FileManagerConflictError("Directory listing changed; refresh and retry")`. It creates a snapshot only for initial items, slices `FILE_MANAGER_PAGE_SIZE` items, and uses the existing `_encode_cursor` and `_listing` methods.

- [ ] **Step 4: Reduce the main method to orchestration**

```python
def _list_recycle_items(
    self,
    cursor: str | None = None,
) -> FileManagerDirectoryListing:
    key = (str(self._workspace_dir), FileManagerRoot.RECYCLE.value, "", "")
    identity = self._recycle_index_identity()
    cursor_state = self._validate_cursor_context(
        cursor, FileManagerRoot.RECYCLE, "", None
    )
    if cursor_state is not None:
        return self._recycle_snapshot_page(key, identity, cursor_state)
    items = [
        listing_item
        for record in self._load_recovered_archive_index().get("items", [])
        if (listing_item := self._recycle_listing_item(record)) is not None
    ]
    items.sort(
        key=lambda item: (
            item.archived_at or datetime.min.replace(tzinfo=timezone.utc),
            item.archive_item_id or "",
        ),
        reverse=True,
    )
    return self._recycle_snapshot_page(key, identity, None, items)
```

Use a signature that fits the local type style, but retain this data flow and leave `_list_recycle_items` at complexity 15 or lower.

- [ ] **Step 5: Run focused unit tests**

Run: `venv/bin/python -m pytest tests/unit/app/test_file_manager.py -q`

Expected: PASS.

- [ ] **Step 6: Run the configured complexity check**

Run the repository command that reports `_list_recycle_items` cognitive complexity.

Expected: no more than 15.

### Task 3: Verify the affected interface and scope

**Files:**

- Verify: `src/swe/app/file_manager.py`
- Verify: `tests/unit/app/test_file_manager.py`

- [ ] **Step 1: Run router contract tests**

Run: `venv/bin/python -m pytest tests/unit/routers/test_console_chat_stream.py -k 'file_manager_recycle' -q`

Expected: PASS.

- [ ] **Step 2: Inspect final changes**

Run: `git diff --check && git diff -- src/swe/app/file_manager.py tests/unit/app/test_file_manager.py`

Expected: no whitespace errors and no unrelated production changes.

- [ ] **Step 3: Detect the graph-level change scope**

Run GitNexus: `detect_changes({scope: "all", repo: "CoPaw"})`.

Expected: only recycle-listing helpers/method and focused tests are newly affected.

- [ ] **Step 4: Commit only with user authorization**

```bash
git add src/swe/app/file_manager.py tests/unit/app/test_file_manager.py
git commit -m "refactor(file-manager): simplify recycle listing"
```

Expected: one intentional refactor commit that excludes pre-existing worktree changes.
