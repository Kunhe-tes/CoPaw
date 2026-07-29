# -*- coding: utf-8 -*-
"""Controlled, tenant-workspace directory access for the chat file manager.

This module deliberately contains no FastAPI routes.  Routers provide tenant
authentication and translate its small, typed surface into HTTP responses.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import hashlib
import hmac
import json
import os
import re
import stat as stat_module
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Mapping

from pydantic import BaseModel

FILE_MANAGER_PAGE_SIZE = 100
FILE_MANAGER_DIRECTORY_SCAN_LIMIT = 10_000
TEXT_PREVIEW_LIMIT_BYTES = 1024 * 1024
_FILE_READ_CHUNK_BYTES = 64 * 1024
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


@dataclass(frozen=True)
class FileManagerReadSnapshot:
    """A bounded read result tied to one safely opened file descriptor."""

    path: str
    size_bytes: int
    modified_at: datetime
    revision: str
    is_text: bool
    is_truncated: bool
    preview_bytes: bytes


def root_capabilities(root: FileManagerRoot | str) -> FileManagerCapabilities:
    try:
        root = FileManagerRoot(root)
    except (TypeError, ValueError) as exc:
        raise FileManagerPathError("Unknown file manager root") from exc
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

        resolved_root, normalised_path = self._validate_root_and_path(
            root,
            relative_path,
        )
        if normalised_path:
            self._reject_symlink_path(resolved_root, normalised_path)
        # This display path is not an access grant.  All filesystem operations
        # below use _open_directory_fd/_open_file_fd with O_NOFOLLOW.
        return normalised_path, self._root_path(resolved_root).joinpath(
            *filter(None, normalised_path.split("/")),
        )

    def list_directory(
        self,
        root: FileManagerRoot | str,
        relative_path: str = "",
        *,
        cursor: str | None = None,
        query: str | None = None,
    ) -> FileManagerDirectoryListing:
        resolved_root, normalised_path = self._validate_root_and_path(
            root,
            relative_path,
        )
        directory_fd = self._open_directory_fd(
            resolved_root,
            normalised_path,
            allow_missing_root=True,
        )
        if directory_fd is None:
            self._validate_cursor_context(
                cursor,
                resolved_root,
                normalised_path,
                query,
            )
            return self._listing(resolved_root, normalised_path, [])
        try:
            items = self._directory_items(
                resolved_root,
                normalised_path,
                directory_fd,
                query,
            )
        finally:
            os.close(directory_fd)
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
        snapshot = self.read_file_snapshot(root, relative_path)
        if not snapshot.is_text:
            return FileManagerTextPreview(
                path=snapshot.path,
                size_bytes=snapshot.size_bytes,
                is_text=False,
                is_truncated=snapshot.is_truncated,
            )
        content = self._decode_preview_bytes(snapshot.preview_bytes)
        return FileManagerTextPreview(
            path=snapshot.path,
            size_bytes=snapshot.size_bytes,
            is_text=True,
            content=content,
            is_truncated=snapshot.is_truncated,
            editable=not snapshot.is_truncated,
        )

    def read_file_snapshot(
        self,
        root: FileManagerRoot | str,
        relative_path: str,
    ) -> FileManagerReadSnapshot:
        """Read a bounded preview and validate the complete file on one fd.

        The snapshot supplies a stable revision hook for subsequent save
        operations without exposing the full file body to callers.
        """

        resolved_root, normalised_path = self._validate_root_and_path(
            root,
            relative_path,
        )
        file_fd = self._open_file_fd(resolved_root, normalised_path)
        try:
            initial_stat = os.fstat(file_fd)
            if not stat_module.S_ISREG(initial_stat.st_mode):
                raise FileManagerPathError("Path is not a regular file")
            preview = bytearray()
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            is_text = True
            has_control_character = False
            with os.fdopen(file_fd, "rb", closefd=False) as handle:
                while chunk := handle.read(_FILE_READ_CHUNK_BYTES):
                    remaining_preview = TEXT_PREVIEW_LIMIT_BYTES - len(preview)
                    if remaining_preview > 0:
                        preview.extend(chunk[:remaining_preview])
                    if not is_text:
                        continue
                    try:
                        decoded_chunk = decoder.decode(chunk, final=False)
                    except UnicodeDecodeError:
                        is_text = False
                        continue
                    if self._contains_disallowed_control_character(
                        decoded_chunk,
                    ):
                        has_control_character = True
                if is_text:
                    try:
                        tail = decoder.decode(b"", final=True)
                    except UnicodeDecodeError:
                        is_text = False
                    else:
                        has_control_character = (
                            has_control_character
                            or self._contains_disallowed_control_character(
                                tail,
                            )
                        )
            final_stat = os.fstat(file_fd)
        except OSError as exc:
            raise FileManagerPathError("Unable to read file") from exc
        finally:
            os.close(file_fd)

        if self._stat_identity(initial_stat) != self._stat_identity(
            final_stat,
        ):
            raise FileManagerPathError("File changed while being read")
        is_text = is_text and not has_control_character
        return FileManagerReadSnapshot(
            path=normalised_path,
            size_bytes=initial_stat.st_size,
            modified_at=datetime.fromtimestamp(
                initial_stat.st_mtime,
                tz=timezone.utc,
            ),
            revision=self._revision_for_stat(initial_stat),
            is_text=is_text,
            is_truncated=initial_stat.st_size > TEXT_PREVIEW_LIMIT_BYTES,
            preview_bytes=bytes(preview),
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
    def _root_components(root: FileManagerRoot) -> tuple[str, ...]:
        suffixes = {
            FileManagerRoot.WORKING: (),
            FileManagerRoot.UPLOAD: ("media",),
            FileManagerRoot.DOWNLOAD: ("static",),
            FileManagerRoot.CONVERSATION: ("sessions",),
        }
        return suffixes[root]

    def _validate_root_and_path(
        self,
        root: FileManagerRoot | str,
        relative_path: str,
    ) -> tuple[FileManagerRoot, str]:
        try:
            resolved_root = FileManagerRoot(root)
        except (TypeError, ValueError) as exc:
            raise FileManagerPathError("Unknown file manager root") from exc
        if resolved_root is FileManagerRoot.RECYCLE:
            raise FileManagerPathError("Recycle paths are not available here")
        normalised_path = self._normalise_relative_path(relative_path)
        if (
            resolved_root is FileManagerRoot.WORKING
            and normalised_path.split("/", 1)[0] in _WORKING_HIDDEN_TOP_LEVEL
        ):
            raise FileManagerPathError("Working path is hidden")
        return resolved_root, normalised_path

    @staticmethod
    def _directory_open_flags() -> int:
        nofollow = getattr(os, "O_NOFOLLOW", None)
        directory = getattr(os, "O_DIRECTORY", None)
        if nofollow is None or directory is None:
            raise FileManagerPathError("Safe directory access is unavailable")
        return os.O_RDONLY | os.O_CLOEXEC | nofollow | directory

    @staticmethod
    def _file_open_flags() -> int:
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            raise FileManagerPathError("Safe file access is unavailable")
        return os.O_RDONLY | os.O_CLOEXEC | nofollow

    def _open_directory_fd(
        self,
        root: FileManagerRoot,
        relative_path: str,
        *,
        allow_missing_root: bool = False,
    ) -> int | None:
        parts = self._root_components(root) + tuple(
            filter(None, relative_path.split("/")),
        )
        try:
            directory_fd = os.open(
                self._workspace_dir,
                self._directory_open_flags(),
            )
        except OSError as exc:
            raise FileManagerPathError("Unable to open workspace") from exc
        try:
            for index, part in enumerate(parts):
                try:
                    child_fd = os.open(
                        part,
                        self._directory_open_flags(),
                        dir_fd=directory_fd,
                    )
                except FileNotFoundError as exc:
                    if (
                        allow_missing_root
                        and relative_path == ""
                        and index == len(parts) - 1
                    ):
                        os.close(directory_fd)
                        return None
                    raise FileManagerPathError(
                        "Directory was not found",
                    ) from exc
                except OSError as exc:
                    raise FileManagerPathError(
                        "Unable to open directory",
                    ) from exc
                os.close(directory_fd)
                directory_fd = child_fd
            return directory_fd
        except Exception:
            try:
                os.close(directory_fd)
            except OSError:
                pass
            raise

    def _open_file_fd(self, root: FileManagerRoot, relative_path: str) -> int:
        parts = tuple(filter(None, relative_path.split("/")))
        if not parts:
            raise FileManagerPathError("Path is not a file")
        parent_path = "/".join(parts[:-1])
        parent_fd = self._open_directory_fd(root, parent_path)
        assert parent_fd is not None
        try:
            return os.open(
                parts[-1],
                self._file_open_flags(),
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise FileManagerPathError("Unable to open file") from exc
        finally:
            os.close(parent_fd)

    def _reject_symlink_path(
        self,
        root: FileManagerRoot,
        relative_path: str,
    ) -> None:
        parts = tuple(filter(None, relative_path.split("/")))
        parent_fd = self._open_directory_fd(root, "/".join(parts[:-1]))
        assert parent_fd is not None
        try:
            try:
                entry_stat = os.stat(
                    parts[-1],
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                return
            if stat_module.S_ISLNK(entry_stat.st_mode):
                raise FileManagerPathError("Symbolic links cannot be followed")
        except OSError as exc:
            raise FileManagerPathError("Unable to inspect path") from exc
        finally:
            os.close(parent_fd)

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
        directory_fd: int,
        query: str | None,
    ) -> list[FileManagerItem]:
        query_value = query.casefold() if query else None
        items: list[FileManagerItem] = []
        try:
            with os.scandir(directory_fd) as entries:
                for scanned_count, entry in enumerate(entries, start=1):
                    if scanned_count > FILE_MANAGER_DIRECTORY_SCAN_LIMIT:
                        raise FileManagerPathError(
                            "Directory contains too many entries",
                        )
                    if (
                        root is FileManagerRoot.WORKING
                        and parent_path == ""
                        and entry.name in _WORKING_HIDDEN_TOP_LEVEL
                    ):
                        continue
                    if (
                        query_value
                        and query_value not in entry.name.casefold()
                    ):
                        continue
                    try:
                        entry_stat = os.stat(
                            entry.name,
                            dir_fd=directory_fd,
                            follow_symlinks=False,
                        )
                    except FileNotFoundError:
                        # An entry removed after scandir is safe to omit.
                        continue
                    except OSError as exc:
                        raise FileManagerPathError(
                            "Unable to inspect directory",
                        ) from exc
                    items.append(
                        self._item_for_entry(
                            root,
                            parent_path,
                            entry.name,
                            entry_stat,
                        ),
                    )
        except FileManagerPathError:
            raise
        except OSError as exc:
            raise FileManagerPathError("Unable to list directory") from exc
        return sorted(items, key=self._item_sort_key)

    def _item_for_entry(
        self,
        root: FileManagerRoot,
        parent_path: str,
        name: str,
        entry_stat: os.stat_result,
    ) -> FileManagerItem:
        path = f"{parent_path}/{name}" if parent_path else name
        if stat_module.S_ISLNK(entry_stat.st_mode):
            return FileManagerItem(
                name=name,
                path=path,
                kind=FileManagerItemKind.SYMLINK,
                capabilities=FileManagerCapabilities(),
            )

        kind = (
            FileManagerItemKind.DIRECTORY
            if stat_module.S_ISDIR(entry_stat.st_mode)
            else FileManagerItemKind.FILE
        )
        capabilities = root_capabilities(root)
        if kind is FileManagerItemKind.FILE:
            capabilities = capabilities.model_copy(
                update={"browse": False, "upload": False},
            )
        return FileManagerItem(
            name=name,
            path=path,
            kind=kind,
            size_bytes=(
                None
                if kind is FileManagerItemKind.DIRECTORY
                else entry_stat.st_size
            ),
            modified_at=datetime.fromtimestamp(
                entry_stat.st_mtime,
                tz=timezone.utc,
            ),
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
    def _decode_preview_bytes(preview_bytes: bytes) -> str:
        try:
            return preview_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            # Complete-file validation succeeded, so only the final preview
            # boundary may cut one otherwise-valid multi-byte code point.
            if exc.reason != "unexpected end of data" or exc.end != len(
                preview_bytes,
            ):
                raise FileManagerPathError(
                    "Invalid UTF-8 preview boundary",
                ) from exc
            return preview_bytes[: exc.start].decode("utf-8")

    @staticmethod
    def _stat_identity(
        entry_stat: os.stat_result,
    ) -> tuple[int, int, int, int]:
        return (
            entry_stat.st_dev,
            entry_stat.st_ino,
            entry_stat.st_size,
            entry_stat.st_mtime_ns,
        )

    @staticmethod
    def _revision_for_stat(entry_stat: os.stat_result) -> str:
        return ":".join(
            str(value)
            for value in (
                entry_stat.st_dev,
                entry_stat.st_ino,
                entry_stat.st_mtime_ns,
                entry_stat.st_size,
            )
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
        last_path = self._validate_cursor_context(cursor, root, path, query)
        try:
            return next(
                index + 1
                for index, item in enumerate(items)
                if item.path == last_path
            )
        except StopIteration as exc:
            raise FileManagerPathError("Invalid directory cursor") from exc

    def _validate_cursor_context(
        self,
        cursor: str | None,
        root: FileManagerRoot,
        path: str,
        query: str | None,
    ) -> str | None:
        if cursor is None:
            return None
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
            last_path = cursor_payload["last_path"]
            if not isinstance(last_path, str):
                raise ValueError
            return last_path
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

    @staticmethod
    def _decode_text_sample(
        sample: bytes,
        *,
        sample_is_truncated: bool,
    ) -> str | None:
        try:
            return sample.decode("utf-8")
        except UnicodeDecodeError as exc:
            if (
                not sample_is_truncated
                or exc.reason != "unexpected end of data"
                or exc.end != len(sample)
            ):
                return None
            return sample[: exc.start].decode("utf-8")

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
