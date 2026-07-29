# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest

from swe.app.file_manager import (
    FILE_MANAGER_PAGE_SIZE,
    FileManagerPathError,
    FileManagerRoot,
    FileManagerService,
)


def _service(workspace: Path) -> FileManagerService:
    return FileManagerService(workspace)


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
