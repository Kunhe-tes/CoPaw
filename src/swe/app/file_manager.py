# -*- coding: utf-8 -*-
"""Controlled, tenant-workspace directory access for the chat file manager.

This module deliberately contains no FastAPI routes.  Routers provide tenant
authentication and translate its small, typed surface into HTTP responses.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import unicodedata
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Mapping

from pydantic import BaseModel

FILE_MANAGER_PAGE_SIZE = 100
TEXT_PREVIEW_LIMIT_BYTES = 1024 * 1024
_WORKING_HIDDEN_TOP_LEVEL = frozenset({"sessions", "governance"})
_NATURAL_PARTS = re.compile(r"(\d+)")


class FileManagerPathError(ValueError):
    """A requested path is outside the controlled directory contract."""


class FileManagerRoot(str, Enum):
    WORKING = "working"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    CONVERSATION = "conversation"
    RECYCLE = "recycle"


class FileManagerItemKind(str, Enum):
    DIRECTORY = "directory"
    FILE = "file"
    SYMLINK = "symlink"


class FileManagerCapabilities(BaseModel):
    browse: bool = False
    read: bool = False
    upload: bool = False
    edit: bool = False
    download: bool = False
    archive: bool = False


class FileManagerItem(BaseModel):
    name: str
    path: str
    kind: FileManagerItemKind
    size_bytes: int | None = None
    modified_at: datetime | None = None
    capabilities: FileManagerCapabilities


class FileManagerDirectoryListing(BaseModel):
    root: FileManagerRoot
    path: str
    items: list[FileManagerItem]
    next_cursor: str | None = None
    has_child_directory: bool = False
    first_child_directory: str | None = None
    capabilities: FileManagerCapabilities


class FileManagerTextPreview(BaseModel):
    path: str
    size_bytes: int
    is_text: bool
    content: str | None = None
    is_truncated: bool = False
    editable: bool = False


def root_capabilities(root: FileManagerRoot | str) -> FileManagerCapabilities:
    root = FileManagerRoot(root)
    if root is FileManagerRoot.CONVERSATION:
        return FileManagerCapabilities(browse=True, read=True, download=True)
    if root is FileManagerRoot.RECYCLE:
        return FileManagerCapabilities()
    return FileManagerCapabilities(
        browse=True,
        read=True,
        upload=True,
        edit=True,
        download=True,
        archive=True,
    )


class FileManagerService:
    """Confines operations to the roots exposed by the chat file manager."""

    def __init__(
        self,
        workspace_dir: Path,
        *,
        cursor_secret: bytes | str,
    ) -> None:
        self._workspace_dir = workspace_dir.resolve()
        self._cursor_secret = (
            cursor_secret.encode("utf-8")
            if isinstance(cursor_secret, str)
            else cursor_secret
        )
        if not self._cursor_secret:
            raise ValueError("cursor_secret must not be empty")

    def resolve_path(
        self,
        root: FileManagerRoot | str,
        relative_path: str = "",
    ) -> tuple[str, Path]:
        """Return a safe, non-symlink path under one controlled root.

        The empty path is the root itself.  All non-empty values must use the
        POSIX relative representation returned to API consumers.
        """

        resolved_root = FileManagerRoot(root)
        if resolved_root is FileManagerRoot.RECYCLE:
            raise FileManagerPathError("Recycle paths are not available here")

        normalised_path = self._normalise_relative_path(relative_path)
        if (
            resolved_root is FileManagerRoot.WORKING
            and normalised_path.split("/", 1)[0] in _WORKING_HIDDEN_TOP_LEVEL
        ):
            raise FileManagerPathError("Working path is hidden")

        base_path = self._root_path(resolved_root)
        if base_path.is_symlink():
            raise FileManagerPathError("Controlled root cannot be a symlink")

        candidate = base_path
        for part in filter(None, normalised_path.split("/")):
            candidate = candidate / part
            if candidate.is_symlink():
                raise FileManagerPathError("Symbolic links cannot be followed")

        try:
            candidate.resolve(strict=False).relative_to(self._workspace_dir)
        except ValueError as exc:
            raise FileManagerPathError("Path escapes workspace") from exc
        return normalised_path, candidate

    def list_directory(
        self,
        root: FileManagerRoot | str,
        relative_path: str = "",
        *,
        cursor: str | None = None,
        query: str | None = None,
    ) -> FileManagerDirectoryListing:
        resolved_root = FileManagerRoot(root)
        normalised_path, directory = self.resolve_path(
            resolved_root,
            relative_path,
        )
        if not directory.exists() and normalised_path == "":
            return self._listing(resolved_root, normalised_path, [])
        if not directory.is_dir():
            raise FileManagerPathError("Path is not a directory")

        items = self._directory_items(
            resolved_root,
            normalised_path,
            directory,
            query,
        )
        start_index = self._cursor_index(
            cursor,
            resolved_root,
            normalised_path,
            query,
            items,
        )
        page = items[start_index : start_index + FILE_MANAGER_PAGE_SIZE]
        next_cursor = None
        if start_index + FILE_MANAGER_PAGE_SIZE < len(items):
            next_cursor = self._encode_cursor(
                resolved_root,
                normalised_path,
                query,
                page[-1].path,
            )
        return self._listing(resolved_root, normalised_path, page, next_cursor)

    def read_text_preview(
        self,
        root: FileManagerRoot | str,
        relative_path: str,
    ) -> FileManagerTextPreview:
        normalised_path, target = self.resolve_path(root, relative_path)
        if not target.is_file():
            raise FileManagerPathError("Path is not a file")

        size_bytes = target.stat().st_size
        with target.open("rb") as handle:
            sample = handle.read(TEXT_PREVIEW_LIMIT_BYTES + 4)
        try:
            decoded_sample = sample.decode("utf-8")
        except UnicodeDecodeError:
            return FileManagerTextPreview(
                path=normalised_path,
                size_bytes=size_bytes,
                is_text=False,
                is_truncated=size_bytes > TEXT_PREVIEW_LIMIT_BYTES,
            )
        if self._contains_disallowed_control_character(decoded_sample):
            return FileManagerTextPreview(
                path=normalised_path,
                size_bytes=size_bytes,
                is_text=False,
                is_truncated=size_bytes > TEXT_PREVIEW_LIMIT_BYTES,
            )

        is_truncated = size_bytes > TEXT_PREVIEW_LIMIT_BYTES
        preview_bytes = (
            sample[:TEXT_PREVIEW_LIMIT_BYTES] if is_truncated else sample
        )
        try:
            content = preview_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            # The full sampled bytes are valid UTF-8.  Therefore a prefix can
            # fail only by ending in one partial UTF-8 code point.
            if not is_truncated or exc.end != len(preview_bytes):
                raise FileManagerPathError(
                    "Invalid UTF-8 preview boundary",
                ) from exc
            content = preview_bytes[: exc.start].decode("utf-8")
        return FileManagerTextPreview(
            path=normalised_path,
            size_bytes=size_bytes,
            is_text=True,
            content=content,
            is_truncated=is_truncated,
            editable=not is_truncated,
        )

    def _root_path(self, root: FileManagerRoot) -> Path:
        suffixes = {
            FileManagerRoot.WORKING: (),
            FileManagerRoot.UPLOAD: ("media",),
            FileManagerRoot.DOWNLOAD: ("static",),
            FileManagerRoot.CONVERSATION: ("sessions",),
        }
        return self._workspace_dir.joinpath(*suffixes[root])

    @staticmethod
    def _normalise_relative_path(relative_path: str) -> str:
        if not isinstance(relative_path, str) or "\\" in relative_path:
            raise FileManagerPathError("Path must be a relative POSIX path")
        if not relative_path:
            return ""
        raw_path = PurePosixPath(relative_path)
        if raw_path.is_absolute() or relative_path in {".", ".."}:
            raise FileManagerPathError("Path must be relative")
        parts = raw_path.parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise FileManagerPathError("Path must not escape its root")
        return "/".join(parts)

    def _directory_items(
        self,
        root: FileManagerRoot,
        parent_path: str,
        directory: Path,
        query: str | None,
    ) -> list[FileManagerItem]:
        query_value = query.casefold() if query else None
        items: list[FileManagerItem] = []
        for entry in directory.iterdir():
            if (
                root is FileManagerRoot.WORKING
                and parent_path == ""
                and entry.name in _WORKING_HIDDEN_TOP_LEVEL
            ):
                continue
            if query_value and query_value not in entry.name.casefold():
                continue
            items.append(self._item_for_entry(root, parent_path, entry))
        return sorted(items, key=self._item_sort_key)

    def _item_for_entry(
        self,
        root: FileManagerRoot,
        parent_path: str,
        entry: Path,
    ) -> FileManagerItem:
        path = f"{parent_path}/{entry.name}" if parent_path else entry.name
        if entry.is_symlink():
            return FileManagerItem(
                name=entry.name,
                path=path,
                kind=FileManagerItemKind.SYMLINK,
                capabilities=FileManagerCapabilities(),
            )

        stat = entry.stat()
        kind = (
            FileManagerItemKind.DIRECTORY
            if entry.is_dir()
            else FileManagerItemKind.FILE
        )
        capabilities = root_capabilities(root)
        if kind is FileManagerItemKind.FILE:
            capabilities = capabilities.model_copy(
                update={"browse": False, "upload": False},
            )
        return FileManagerItem(
            name=entry.name,
            path=path,
            kind=kind,
            size_bytes=(
                None if kind is FileManagerItemKind.DIRECTORY else stat.st_size
            ),
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            capabilities=capabilities,
        )

    @staticmethod
    def _contains_disallowed_control_character(text: str) -> bool:
        return any(
            unicodedata.category(character) == "Cc"
            and character not in {"\t", "\n", "\r"}
            for character in text
        )

    @staticmethod
    def _item_sort_key(
        item: FileManagerItem,
    ) -> tuple[int, tuple[tuple[int, int | str], ...], str]:
        kind_rank = 0 if item.kind is FileManagerItemKind.DIRECTORY else 1
        natural_name = tuple(
            (0, int(part)) if part.isdecimal() else (1, part.casefold())
            for part in _NATURAL_PARTS.split(item.name)
            if part != ""
        )
        return kind_rank, natural_name, item.name

    def _listing(
        self,
        root: FileManagerRoot,
        path: str,
        items: list[FileManagerItem],
        next_cursor: str | None = None,
    ) -> FileManagerDirectoryListing:
        first_directory = next(
            (
                item.path
                for item in items
                if item.kind is FileManagerItemKind.DIRECTORY
            ),
            None,
        )
        return FileManagerDirectoryListing(
            root=root,
            path=path,
            items=items,
            next_cursor=next_cursor,
            has_child_directory=first_directory is not None,
            first_child_directory=first_directory,
            capabilities=root_capabilities(root),
        )

    def _cursor_index(
        self,
        cursor: str | None,
        root: FileManagerRoot,
        path: str,
        query: str | None,
        items: list[FileManagerItem],
    ) -> int:
        if cursor is None:
            return 0
        try:
            encoded_payload = base64.b64decode(
                cursor.encode("ascii"),
                altchars=b"-_",
                validate=True,
            )
            cursor_payload = json.loads(encoded_payload)
            signature = cursor_payload.pop("signature")
            if not isinstance(signature, str) or not hmac.compare_digest(
                signature,
                self._cursor_signature(cursor_payload),
            ):
                raise ValueError
            if cursor_payload != {
                "root": root.value,
                "path": path,
                "query": query or "",
                "version": 1,
                "last_path": cursor_payload["last_path"],
            }:
                raise ValueError
            return next(
                index + 1
                for index, item in enumerate(items)
                if item.path == cursor_payload["last_path"]
            )
        except (
            AttributeError,
            binascii.Error,
            KeyError,
            StopIteration,
            TypeError,
            UnicodeDecodeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise FileManagerPathError("Invalid directory cursor") from exc

    def _encode_cursor(
        self,
        root: FileManagerRoot,
        path: str,
        query: str | None,
        last_path: str,
    ) -> str:
        payload: dict[str, str | int] = {
            "root": root.value,
            "path": path,
            "query": query or "",
            "version": 1,
            "last_path": last_path,
        }
        payload["signature"] = self._cursor_signature(payload)
        return base64.urlsafe_b64encode(
            json.dumps(
                payload,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8"),
        ).decode("ascii")

    def _cursor_signature(self, payload: Mapping[str, object]) -> str:
        canonical_payload = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hmac.new(
            self._cursor_secret,
            canonical_payload,
            hashlib.sha256,
        ).hexdigest()
