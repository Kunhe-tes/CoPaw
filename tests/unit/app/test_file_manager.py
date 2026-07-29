# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

import pytest

from swe.app import file_manager
from swe.app.file_manager import (
    FILE_MANAGER_PAGE_SIZE,
    FileManagerConflictError,
    FileManagerItemKind,
    FileManagerPathError,
    FileManagerRoot,
    FileManagerService,
    root_capabilities,
)


def _service(workspace: Path) -> FileManagerService:
    return FileManagerService(
        workspace,
        cursor_secret=b"test-file-manager-secret",
    )


def test_service_factory_uses_configured_cursor_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SWE_FILE_MANAGER_CURSOR_SECRET", "configured-secret")

    service = file_manager.get_file_manager_service(tmp_path)

    assert service._cursor_secret == b"configured-secret"


def test_service_factory_persists_a_private_fallback_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_dir = tmp_path / "secrets"
    monkeypatch.delenv("SWE_FILE_MANAGER_CURSOR_SECRET", raising=False)
    monkeypatch.setattr(file_manager, "SECRET_DIR", secret_dir)

    first = file_manager.get_file_manager_service(tmp_path / "tenant-a")
    second = file_manager.get_file_manager_service(tmp_path / "tenant-b")

    secret_file = secret_dir / "file-manager-cursor-secret"
    assert first._cursor_secret == second._cursor_secret
    assert len(first._cursor_secret) >= 32
    assert secret_file.exists()
    assert secret_file.stat().st_mode & 0o077 == 0


def test_service_factory_rejects_an_explicit_empty_cursor_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SWE_FILE_MANAGER_CURSOR_SECRET", "")

    with pytest.raises(ValueError, match="must not be empty"):
        file_manager.get_file_manager_service(tmp_path)


def test_working_listing_hides_only_sessions_and_governance(
    tmp_path: Path,
) -> None:
    (tmp_path / "sessions").mkdir()
    (tmp_path / "governance").mkdir()
    (tmp_path / ".env").write_text("visible", encoding="utf-8")
    (tmp_path / "notes").mkdir()

    listing = _service(tmp_path).list_directory(FileManagerRoot.WORKING)

    assert [item.name for item in listing.items] == ["notes", ".env"]


def test_listing_sorts_directories_first_with_case_insensitive_natural_order(
    tmp_path: Path,
) -> None:
    for name in ("zeta", "Folder10", "folder2"):
        (tmp_path / name).mkdir()
    for name in ("item10.txt", "Item2.txt", "alpha.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    listing = _service(tmp_path).list_directory(FileManagerRoot.WORKING)

    assert [item.name for item in listing.items] == [
        "folder2",
        "Folder10",
        "zeta",
        "alpha.txt",
        "Item2.txt",
        "item10.txt",
    ]
    assert listing.first_child_directory == "folder2"
    assert listing.has_child_directory is True


def test_natural_sort_handles_leading_numeric_and_alphabetic_names(
    tmp_path: Path,
) -> None:
    for name in ("alpha.txt", "10.txt", "2.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    listing = _service(tmp_path).list_directory(FileManagerRoot.WORKING)

    assert [item.name for item in listing.items] == [
        "2.txt",
        "10.txt",
        "alpha.txt",
    ]


def test_listing_reports_no_child_directory_state(tmp_path: Path) -> None:
    (tmp_path / "only-file.txt").write_text("text", encoding="utf-8")

    listing = _service(tmp_path).list_directory(FileManagerRoot.WORKING)

    assert listing.has_child_directory is False
    assert listing.first_child_directory is None


def test_listing_uses_stable_100_item_cursor_pages(tmp_path: Path) -> None:
    for index in range(FILE_MANAGER_PAGE_SIZE + 2):
        (tmp_path / f"item{index:03d}.txt").write_text("x", encoding="utf-8")

    service = _service(tmp_path)
    first_page = service.list_directory(FileManagerRoot.WORKING)
    second_page = service.list_directory(
        FileManagerRoot.WORKING,
        cursor=first_page.next_cursor,
    )

    assert len(first_page.items) == FILE_MANAGER_PAGE_SIZE
    assert first_page.next_cursor is not None
    assert [item.name for item in second_page.items] == [
        "item100.txt",
        "item101.txt",
    ]
    assert second_page.next_cursor is None


def test_listing_allows_more_than_ten_thousand_items_with_cursor(
    tmp_path: Path,
) -> None:
    for index in range(10_001):
        (tmp_path / f"item{index:05d}.txt").write_text("x", encoding="utf-8")

    listing = _service(tmp_path).list_directory(FileManagerRoot.WORKING)

    assert len(listing.items) == FILE_MANAGER_PAGE_SIZE
    assert listing.items[0].name == "item00000.txt"
    assert listing.items[-1].name == "item00099.txt"
    assert listing.next_cursor is not None


def test_cursor_rejects_forgery_and_context_mismatches(tmp_path: Path) -> None:
    for index in range(FILE_MANAGER_PAGE_SIZE + 1):
        (tmp_path / f"item{index:03d}.txt").write_text("x", encoding="utf-8")
    (tmp_path / "media").mkdir()
    (tmp_path / "folder").mkdir()
    service = _service(tmp_path)
    cursor = service.list_directory(FileManagerRoot.WORKING).next_cursor
    assert cursor is not None

    payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
    payload["last_path"] = "item099.txt"
    forged_cursor = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    ).decode("ascii")

    for root, path, query, candidate in (
        (FileManagerRoot.WORKING, "", None, forged_cursor),
        (FileManagerRoot.UPLOAD, "", None, cursor),
        (FileManagerRoot.WORKING, "folder", None, cursor),
        (FileManagerRoot.WORKING, "", "item", cursor),
        (FileManagerRoot.WORKING, "missing", None, cursor),
    ):
        with pytest.raises(FileManagerPathError):
            service.list_directory(root, path, cursor=candidate, query=query)


def test_missing_root_validates_a_cross_context_cursor_before_returning_empty(
    tmp_path: Path,
) -> None:
    for index in range(FILE_MANAGER_PAGE_SIZE + 1):
        (tmp_path / f"item{index:03d}.txt").write_text("x", encoding="utf-8")
    service = _service(tmp_path)
    cursor = service.list_directory(FileManagerRoot.WORKING).next_cursor
    assert cursor is not None

    with pytest.raises(FileManagerPathError):
        service.list_directory(FileManagerRoot.UPLOAD, cursor=cursor)


def test_listing_filters_direct_children_case_insensitively(
    tmp_path: Path,
) -> None:
    (tmp_path / "Report.MD").write_text("report", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "nested-report.md").write_text(
        "nested",
        encoding="utf-8",
    )
    (tmp_path / "other.txt").write_text("other", encoding="utf-8")

    listing = _service(tmp_path).list_directory(
        FileManagerRoot.WORKING,
        query="REpOrT",
    )

    assert [item.name for item in listing.items] == ["reports", "Report.MD"]


@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "../outside", "folder/../../outside"],
)
def test_rejects_absolute_and_escaping_paths(
    tmp_path: Path,
    path: str,
) -> None:
    with pytest.raises(FileManagerPathError):
        _service(tmp_path).resolve_path(FileManagerRoot.WORKING, path)


def test_rejects_backslash_paths(tmp_path: Path) -> None:
    with pytest.raises(FileManagerPathError):
        _service(tmp_path).resolve_path(
            FileManagerRoot.WORKING,
            r"folder\\file.txt",
        )


def test_rejects_recycle_paths_in_this_service(tmp_path: Path) -> None:
    with pytest.raises(FileManagerPathError):
        _service(tmp_path).resolve_path(
            FileManagerRoot.RECYCLE,
            "archived-file",
        )


@pytest.mark.parametrize(
    "path",
    ["sessions", "sessions/chat.json", "governance/archive"],
)
def test_working_root_rejects_hidden_controlled_paths(
    tmp_path: Path,
    path: str,
) -> None:
    with pytest.raises(FileManagerPathError):
        _service(tmp_path).resolve_path(FileManagerRoot.WORKING, path)


@pytest.mark.parametrize(
    ("root", "directory"),
    [
        (FileManagerRoot.WORKING, ""),
        (FileManagerRoot.UPLOAD, "media"),
        (FileManagerRoot.DOWNLOAD, "static"),
        (FileManagerRoot.CONVERSATION, "sessions"),
    ],
)
def test_resolves_each_normal_root_from_workspace(
    tmp_path: Path,
    root: FileManagerRoot,
    directory: str,
) -> None:
    if directory:
        (tmp_path / directory).mkdir()

    relative_path, resolved_path = _service(tmp_path).resolve_path(root, "")

    assert relative_path == ""
    assert resolved_path == tmp_path / directory


def test_symlink_is_listed_without_capabilities_and_never_followed(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("do not expose", encoding="utf-8")
    (tmp_path / "outside-link").symlink_to(outside)

    service = _service(tmp_path)
    item = service.list_directory(FileManagerRoot.WORKING).items[0]

    assert item.kind == "symlink"
    assert item.capabilities.model_dump() == {
        "browse": False,
        "read": False,
        "upload": False,
        "edit": False,
        "download": False,
        "archive": False,
    }
    with pytest.raises(FileManagerPathError):
        service.resolve_path(FileManagerRoot.WORKING, "outside-link")


def test_conversation_root_is_read_and_download_only(tmp_path: Path) -> None:
    (tmp_path / "sessions").mkdir()

    capabilities = (
        _service(tmp_path)
        .list_directory(
            FileManagerRoot.CONVERSATION,
        )
        .capabilities
    )

    assert capabilities.model_dump() == {
        "browse": True,
        "read": True,
        "upload": False,
        "edit": False,
        "download": True,
        "archive": False,
    }


def test_file_items_do_not_expose_directory_browse_or_upload_actions(
    tmp_path: Path,
) -> None:
    (tmp_path / "document.txt").write_text("text", encoding="utf-8")

    item = _service(tmp_path).list_directory(FileManagerRoot.WORKING).items[0]

    assert item.capabilities.browse is False
    assert item.capabilities.upload is False


@pytest.mark.parametrize(
    "root",
    [
        FileManagerRoot.WORKING,
        FileManagerRoot.UPLOAD,
        FileManagerRoot.DOWNLOAD,
    ],
)
def test_mutable_roots_expose_the_full_directory_capability_set(
    tmp_path: Path,
    root: FileManagerRoot,
) -> None:
    if root is FileManagerRoot.UPLOAD:
        (tmp_path / "media").mkdir()
    if root is FileManagerRoot.DOWNLOAD:
        (tmp_path / "static").mkdir()

    capabilities = _service(tmp_path).list_directory(root).capabilities

    assert capabilities.model_dump() == {
        "browse": True,
        "read": True,
        "upload": True,
        "edit": True,
        "download": True,
        "archive": True,
    }


def test_recycle_root_exposes_only_listing_capability() -> None:
    assert root_capabilities(FileManagerRoot.RECYCLE).model_dump() == {
        "browse": True,
        "read": False,
        "upload": False,
        "edit": False,
        "download": False,
        "archive": False,
    }


def test_text_preview_reads_at_most_one_megabyte_and_marks_large_text_read_only(
    tmp_path: Path,
) -> None:
    full_text = "a" * (1024 * 1024)
    (tmp_path / "large.html").write_text(full_text + "tail", encoding="utf-8")

    preview = _service(tmp_path).read_text_preview(
        FileManagerRoot.WORKING,
        "large.html",
    )

    assert preview.is_text is True
    assert preview.is_truncated is True
    assert preview.editable is False
    assert preview.content == full_text
    assert preview.size_bytes == 1024 * 1024 + 4


def test_small_utf8_text_is_fully_read_and_editable(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("你好，Markdown", encoding="utf-8")

    preview = _service(tmp_path).read_text_preview(
        FileManagerRoot.WORKING,
        "README.md",
    )

    assert preview.content == "你好，Markdown"
    assert preview.is_text is True
    assert preview.is_truncated is False
    assert preview.editable is True


@pytest.mark.parametrize(
    "content",
    [b"text\x07bell", b"text\x1bescape", b"text\x7fdelete"],
)
def test_utf8_files_with_disallowed_control_characters_are_not_editable_text(
    tmp_path: Path,
    content: bytes,
) -> None:
    (tmp_path / "control.txt").write_bytes(content)

    preview = _service(tmp_path).read_text_preview(
        FileManagerRoot.WORKING,
        "control.txt",
    )

    assert preview.is_text is False
    assert preview.content is None
    assert preview.editable is False


def test_large_text_rejects_invalid_utf8_instead_of_ignoring_it(
    tmp_path: Path,
) -> None:
    prefix = b"a" * (1024 * 1024 - 1)
    (tmp_path / "invalid.txt").write_bytes(prefix + b"\xfftail")

    preview = _service(tmp_path).read_text_preview(
        FileManagerRoot.WORKING,
        "invalid.txt",
    )

    assert preview.is_text is False
    assert preview.content is None
    assert preview.editable is False


def test_large_utf8_with_codepoint_started_after_sample_is_still_text(
    tmp_path: Path,
) -> None:
    prefix = b"a" * (1024 * 1024 + 3)
    (tmp_path / "boundary.txt").write_bytes(
        prefix + "😀".encode("utf-8") + b"tail",
    )

    preview = _service(tmp_path).read_text_preview(
        FileManagerRoot.WORKING,
        "boundary.txt",
    )

    assert preview.is_text is True
    assert preview.is_truncated is True
    assert preview.editable is False
    assert preview.content == "a" * (1024 * 1024)


def test_large_invalid_utf8_after_sample_boundary_is_rejected(
    tmp_path: Path,
) -> None:
    prefix = b"a" * (1024 * 1024 + 3)
    (tmp_path / "invalid-boundary.txt").write_bytes(
        prefix + b"\xf0\x28invalid",
    )

    preview = _service(tmp_path).read_text_preview(
        FileManagerRoot.WORKING,
        "invalid-boundary.txt",
    )

    assert preview.is_text is False
    assert preview.content is None


def test_large_text_with_invalid_utf8_after_preview_is_rejected(
    tmp_path: Path,
) -> None:
    (tmp_path / "late-invalid.txt").write_bytes(
        b"a" * (1024 * 1024 + 1024) + b"\xff",
    )

    preview = _service(tmp_path).read_text_preview(
        FileManagerRoot.WORKING,
        "late-invalid.txt",
    )

    assert preview.is_text is False
    assert preview.content is None
    assert preview.editable is False


def test_file_read_rejects_a_symlink_without_following_its_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.txt"
    target.write_text("private", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(target)

    with pytest.raises(FileManagerPathError):
        _service(tmp_path).read_text_preview(
            FileManagerRoot.WORKING,
            "link.txt",
        )


@pytest.mark.parametrize(
    "operation",
    [
        lambda service: service.list_directory("unknown"),
        lambda service: service.list_directory(
            FileManagerRoot.WORKING,
            "missing",
        ),
        lambda service: service.read_text_preview(
            FileManagerRoot.WORKING,
            "missing.txt",
        ),
    ],
)
def test_unknown_or_missing_paths_raise_stable_file_manager_errors(
    tmp_path: Path,
    operation,
) -> None:
    with pytest.raises(FileManagerPathError):
        operation(_service(tmp_path))


def test_directory_listing_has_no_hard_scan_limit(
    tmp_path: Path,
) -> None:
    for name in ("one.txt", "two.txt", "three.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    listing = _service(tmp_path).list_directory(FileManagerRoot.WORKING)

    assert [item.name for item in listing.items] == [
        "one.txt",
        "three.txt",
        "two.txt",
    ]


def test_permission_failures_are_translated_to_file_manager_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def denied(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("swe.app.file_manager.os.open", denied)

    with pytest.raises(FileManagerPathError):
        _service(tmp_path).list_directory(FileManagerRoot.WORKING)


def test_read_snapshot_has_bounded_preview_and_revision_hook(
    tmp_path: Path,
) -> None:
    (tmp_path / "document.md").write_text("content", encoding="utf-8")

    snapshot = _service(tmp_path).read_file_snapshot(
        FileManagerRoot.WORKING,
        "document.md",
    )

    assert snapshot.preview_bytes == b"content"
    assert snapshot.revision == hashlib.sha256(b"content").hexdigest()
    assert snapshot.size_bytes == len(snapshot.preview_bytes)


def test_save_text_requires_matching_revision_and_replaces_safely(
    tmp_path: Path,
) -> None:
    path = tmp_path / "document.md"
    path.write_text("before", encoding="utf-8")
    service = _service(tmp_path)
    revision = service.read_text_preview("working", "document.md").revision

    result = service.save_text(
        "working",
        "document.md",
        "after",
        revision,
    )

    assert path.read_text(encoding="utf-8") == "after"
    assert result.revision != revision
    with pytest.raises(FileManagerConflictError):
        service.save_text("working", "document.md", "lost", revision)
    assert path.read_text(encoding="utf-8") == "after"


def test_content_revision_rejects_same_stat_content_replacement(
    tmp_path: Path,
) -> None:
    path = tmp_path / "document.md"
    path.write_text("before", encoding="utf-8")
    service = _service(tmp_path)
    revision = service.read_text_preview("working", "document.md").revision
    original_stat = path.stat()

    path.write_text("after!", encoding="utf-8")
    os.utime(
        path,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )

    with pytest.raises(FileManagerConflictError):
        service.save_text("working", "document.md", "lost", revision)


def test_archive_rejects_fifo_without_opening_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fifo = tmp_path / "events.pipe"
    os.mkfifo(fifo)
    service = _service(tmp_path)
    original_open = file_manager.os.open

    def fail_if_fifo_open(path, *args, **kwargs):
        if path == "events.pipe":
            raise AssertionError("FIFO must not be opened")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(file_manager.os, "open", fail_if_fifo_open)
    listing = service.list_directory("working")

    assert listing.items[0].kind is FileManagerItemKind.SPECIAL
    assert listing.items[0].capabilities.model_dump() == {
        "browse": False,
        "read": False,
        "upload": False,
        "edit": False,
        "download": False,
        "archive": False,
    }
    with pytest.raises(FileManagerPathError):
        service.archive_file("working", "events.pipe", actor="tester")


@pytest.mark.parametrize("operation", ["archive", "restore", "purge"])
def test_recycle_mutations_restore_visible_state_when_index_save_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    path = tmp_path / "report.txt"
    path.write_text("report", encoding="utf-8")
    service = _service(tmp_path)
    archived = None
    if operation != "archive":
        archived = service.archive_file(
            "working",
            "report.txt",
            actor="tester",
        )

    def fail_index_save(*args, **kwargs):
        raise OSError("index unavailable")

    monkeypatch.setattr(file_manager, "save_archive_index", fail_index_save)
    with pytest.raises((FileManagerPathError, OSError)):
        if operation == "archive":
            service.archive_file("working", "report.txt", actor="tester")
        elif operation == "restore":
            assert archived is not None
            service.restore_recycle_item(
                archived.archive_item_id,
                actor="tester",
            )
        else:
            assert archived is not None
            service.purge_recycle_item(
                archived.archive_item_id,
                actor="tester",
            )

    if operation == "archive":
        assert path.read_text(encoding="utf-8") == "report"
        assert not (
            tmp_path / "governance" / "archive" / "files"
        ).exists() or not list(
            (tmp_path / "governance" / "archive" / "files").iterdir(),
        )
    elif operation == "restore":
        assert not path.exists()
        assert archived is not None
        assert (
            tmp_path
            / "governance"
            / "archive"
            / "files"
            / archived.archive_item_id
        ).is_file()
    else:
        assert archived is not None
        assert (
            tmp_path
            / "governance"
            / "archive"
            / "files"
            / archived.archive_item_id
        ).is_file()


@pytest.mark.parametrize(
    "root,path,content",
    [
        ("conversation", "chat.txt", "no"),
        ("working", "binary.bin", "no"),
        ("working", "large.txt", "no"),
    ],
)
def test_save_text_rejects_noneditable_file_snapshots(
    tmp_path: Path,
    root: str,
    path: str,
    content: str,
) -> None:
    if root == "conversation":
        (tmp_path / "sessions").mkdir()
        target = tmp_path / "sessions" / path
        target.write_text("chat", encoding="utf-8")
    else:
        target = tmp_path / path
        target.write_bytes(
            (
                b"\x00binary"
                if path.endswith(".bin")
                else b"x" * (1024 * 1024 + 1)
            ),
        )
    service = _service(tmp_path)
    revision = service.read_text_preview(root, path).revision

    with pytest.raises(FileManagerPathError):
        service.save_text(root, path, content, revision)


def test_upload_rejects_collisions_and_never_writes_through_links(
    tmp_path: Path,
) -> None:
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "exists.txt").write_text("old", encoding="utf-8")
    outside = tmp_path.parent / "file-manager-upload-outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (tmp_path / "media" / "link.txt").symlink_to(outside)
    service = _service(tmp_path)

    with pytest.raises(FileManagerConflictError):
        service.upload_bytes("upload", "", "exists.txt", b"new")
    with pytest.raises(FileManagerConflictError):
        service.upload_bytes("upload", "", "link.txt", b"new")
    uploaded = service.upload_bytes("upload", "", "fresh.txt", b"fresh")

    assert uploaded.path == "fresh.txt"
    assert (tmp_path / "media" / "fresh.txt").read_bytes() == b"fresh"
    assert outside.read_text(encoding="utf-8") == "outside"


@pytest.mark.parametrize("root", ["conversation", "recycle"])
def test_upload_rejects_read_only_roots(tmp_path: Path, root: str) -> None:
    (tmp_path / "sessions").mkdir()
    with pytest.raises(FileManagerPathError):
        _service(tmp_path).upload_bytes(root, "", "upload.txt", b"body")


def test_archive_restore_and_purge_recycle_items_without_exposing_payload_paths(
    tmp_path: Path,
) -> None:
    path = tmp_path / "MEMORY.md"
    path.write_text("user editable through file manager", encoding="utf-8")
    service = _service(tmp_path)

    archived = service.archive_file("working", "MEMORY.md", actor="tester")
    listing = service.list_directory("recycle")

    assert not path.exists()
    assert listing.items[0].archive_item_id == archived.archive_item_id
    assert listing.items[0].original_path == "MEMORY.md"
    assert listing.items[0].archived_at is not None
    assert "governance/archive/files" not in listing.items[0].model_dump_json()

    (tmp_path / "MEMORY.md").write_text("collision", encoding="utf-8")
    with pytest.raises(FileManagerConflictError):
        service.restore_recycle_item(archived.archive_item_id, actor="tester")
    assert (
        listing.items[0].archive_item_id
        == service.list_directory("recycle").items[0].archive_item_id
    )
    path.unlink()

    restored = service.restore_recycle_item(
        archived.archive_item_id,
        actor="tester",
    )
    assert restored.original_path == "MEMORY.md"
    assert (
        path.read_text(encoding="utf-8")
        == "user editable through file manager"
    )

    second = service.archive_file("working", "MEMORY.md", actor="tester")
    service.purge_recycle_item(second.archive_item_id, actor="tester")
    assert service.list_directory("recycle").items == []
