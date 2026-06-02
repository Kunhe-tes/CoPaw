# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long
import asyncio
from contextlib import suppress
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Optional

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from .utils import (
    truncate_text_output,
    read_file_safe,
    DEFAULT_MAX_BYTES,
)
from ...config.context import (
    get_current_file_read_max_bytes,
    get_current_recent_max_bytes,
)
from ...constant import TRUNCATION_NOTICE_MARKER
from ...security.tenant_path_boundary import (
    resolve_tenant_path,
    TenantPathBoundaryError,
    make_permission_denied_response,
    get_current_tool_base_dir,
    get_current_tenant_root,
)

logger = logging.getLogger(__name__)
_FILE_WRITE_LOCKS: dict[str, asyncio.Lock] = {}
_FILE_WRITE_LOCKS_GUARD = threading.Lock()

try:
    FILE_WRITE_SLOW_WARNING_SECONDS = max(
        float(os.environ.get("SWE_FILE_WRITE_SLOW_WARNING_SECONDS", "1.0")),
        0.0,
    )
except (TypeError, ValueError):
    FILE_WRITE_SLOW_WARNING_SECONDS = 1.0


def _resolve_file_path(file_path: str) -> str:
    """Resolve file path using tenant path boundary.

    All paths are resolved against the current agent's workspace directory
    (when available) or the current tenant's workspace root, and validated
    to ensure they stay within WORKING_DIR/<tenant_id>.

    Args:
        file_path: The input file path (absolute or relative).

    Returns:
        The resolved absolute file path as string.

    Raises:
        TenantPathBoundaryError: If the path escapes the tenant workspace
                                 or tenant context is missing.
    """
    base_dir = get_current_tool_base_dir()
    resolved = resolve_tenant_path(
        file_path,
        base_dir=base_dir,
        allow_nonexistent=True,
    )
    return str(resolved)


def _resolve_writable_file_path(file_path: str) -> str:
    base_dir = get_current_tool_base_dir()
    try:
        return _resolve_file_path(file_path)
    except TenantPathBoundaryError:
        expanded_path = os.path.expanduser(file_path)
        path_obj = Path(expanded_path)
        tenant_root = get_current_tenant_root().resolve()
        candidate = (
            path_obj if path_obj.is_absolute() else (base_dir / path_obj)
        ).resolve(strict=False)

        try:
            candidate.relative_to(tenant_root)
        except ValueError as exc:
            raise TenantPathBoundaryError(
                "Write target escapes the tenant workspace boundary.",
                resolved_path=candidate,
            ) from exc

        candidate.parent.mkdir(parents=True, exist_ok=True)
        return str(candidate)


def _get_encoding_for_file(file_path: str) -> str:
    """Determine the appropriate encoding for a file based on its type.

    For cross-platform compatibility, especially with Windows Excel/Notepad:
    - CSV/TSV/TXT files: Use UTF-8-BOM (Windows Excel needs BOM to detect UTF-8)
    - All other files: Use UTF-8 (safer default, no BOM)

    Args:
        file_path: Path to the file

    Returns:
        Encoding string: "utf-8-sig" or "utf-8"
    """
    suffix = Path(file_path).suffix.lower()

    # Files that need BOM for Windows compatibility
    if suffix in {".csv", ".tsv", ".tab", ".txt", ".log"}:
        return "utf-8-sig"

    # Default: UTF-8 without BOM (safe for all other files)
    # This includes: .sh, .yaml, .json, .py, .js, .md, etc.
    return "utf-8"


def _content_byte_length(content: str, encoding: str) -> int:
    try:
        return len(content.encode(encoding))
    except Exception:
        return len(content.encode("utf-8", errors="replace"))


def _log_file_write_diagnostics(
    *,
    operation: str,
    file_path: str,
    content_bytes: int,
    resolve_seconds: float,
    open_seconds: float,
    write_seconds: float,
    close_seconds: float,
) -> None:
    total_seconds = (
        resolve_seconds + open_seconds + write_seconds + close_seconds
    )
    message = (
        "file_write_diagnostic operation=%s path=%s content_bytes=%d "
        "resolve_seconds=%.6f open_seconds=%.6f write_seconds=%.6f "
        "close_seconds=%.6f total_seconds=%.6f"
    )
    args = (
        operation,
        file_path,
        content_bytes,
        resolve_seconds,
        open_seconds,
        write_seconds,
        close_seconds,
        total_seconds,
    )
    logger.debug(message, *args)
    if total_seconds > FILE_WRITE_SLOW_WARNING_SECONDS:
        logger.warning(message, *args)


def _get_file_write_lock(file_path: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock_key = f"{id(loop)}:{file_path}"
    with _FILE_WRITE_LOCKS_GUARD:
        lock = _FILE_WRITE_LOCKS.get(lock_key)
        if lock is None:
            lock = asyncio.Lock()
            _FILE_WRITE_LOCKS[lock_key] = lock
        return lock


def _make_temp_file_path(file_path: str) -> str:
    target = Path(file_path)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    os.close(fd)
    return temp_path


def _remove_temp_file(temp_path: str) -> None:
    with suppress(OSError):
        os.unlink(temp_path)


def _write_content_with_diagnostics(
    *,
    operation: str,
    file_path: str,
    content: str,
    mode: str,
    encoding: str,
    resolve_seconds: float,
    diagnostic_path: str | None = None,
) -> None:
    open_seconds = 0.0
    write_seconds = 0.0
    close_seconds = 0.0
    started_at = time.perf_counter()
    with open(file_path, mode, encoding=encoding) as file:
        open_seconds = time.perf_counter() - started_at

        started_at = time.perf_counter()
        file.write(content)
        write_seconds = time.perf_counter() - started_at

        started_at = time.perf_counter()
    close_seconds = time.perf_counter() - started_at
    _log_file_write_diagnostics(
        operation=operation,
        file_path=diagnostic_path or file_path,
        content_bytes=_content_byte_length(content, encoding),
        resolve_seconds=resolve_seconds,
        open_seconds=open_seconds,
        write_seconds=write_seconds,
        close_seconds=close_seconds,
    )


def _cleanup_temp_file_after_cancel(
    task: asyncio.Task,
    temp_path: str,
) -> None:
    with suppress(BaseException):
        task.exception()
    _remove_temp_file(temp_path)


async def _write_file_atomically_unlocked(
    *,
    operation: str,
    file_path: str,
    content: str,
    encoding: str,
    resolve_seconds: float,
) -> None:
    temp_path = _make_temp_file_path(file_path)
    write_task = asyncio.create_task(
        asyncio.to_thread(
            _write_content_with_diagnostics,
            operation=operation,
            file_path=temp_path,
            content=content,
            mode="w",
            encoding=encoding,
            resolve_seconds=resolve_seconds,
            diagnostic_path=file_path,
        ),
    )
    try:
        await asyncio.shield(write_task)
        os.replace(temp_path, file_path)
    except asyncio.CancelledError:
        write_task.add_done_callback(
            lambda task: _cleanup_temp_file_after_cancel(task, temp_path),
        )
        raise
    except Exception:
        _remove_temp_file(temp_path)
        raise
    _remove_temp_file(temp_path)


async def _write_file_atomically_with_diagnostics(
    *,
    operation: str,
    file_path: str,
    content: str,
    encoding: str,
    resolve_seconds: float,
) -> None:
    async with _get_file_write_lock(file_path):
        await _write_file_atomically_unlocked(
            operation=operation,
            file_path=file_path,
            content=content,
            encoding=encoding,
            resolve_seconds=resolve_seconds,
        )


def _read_existing_file_content(file_path: str, encoding: str) -> str:
    if not os.path.exists(file_path):
        return ""
    with open(file_path, "r", encoding=encoding) as file:
        return file.read()


async def _append_file_atomically_with_diagnostics(
    *,
    file_path: str,
    content: str,
    encoding: str,
    resolve_seconds: float,
) -> None:
    async with _get_file_write_lock(file_path):
        existing = await asyncio.to_thread(
            _read_existing_file_content,
            file_path,
            encoding,
        )
        await _write_file_atomically_unlocked(
            operation="append_file",
            file_path=file_path,
            content=existing + content,
            encoding=encoding,
            resolve_seconds=resolve_seconds,
        )


async def read_file(  # pylint: disable=too-many-return-statements
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> ToolResponse:
    """Read a file. Relative paths resolve from the current agent workspace
    when available, otherwise the current tenant workspace root.

    Use start_line/end_line to read a specific line range (output includes
    line numbers). Omit both to read the full file.

    Args:
        file_path (`str`):
            Path to the file.
        start_line (`int`, optional):
            First line to read (1-based, inclusive).
        end_line (`int`, optional):
            Last line to read (1-based, inclusive).
    """

    # Convert start_line/end_line to int if they are strings
    if start_line is not None:
        try:
            start_line = int(start_line)
        except (ValueError, TypeError):
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: start_line must be an integer, got {start_line!r}.",
                    ),
                ],
            )

    if end_line is not None:
        try:
            end_line = int(end_line)
        except (ValueError, TypeError):
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: end_line must be an integer, got {end_line!r}.",
                    ),
                ],
            )

    # Validate path against tenant boundary
    try:
        file_path = _resolve_file_path(file_path)
    except TenantPathBoundaryError:
        return ToolResponse(
            content=[
                TextBlock(**make_permission_denied_response("Read file")),
            ],
        )

    if not os.path.exists(file_path):
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: The file {file_path} does not exist.",
                ),
            ],
        )

    if not os.path.isfile(file_path):
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: The path {file_path} is not a file.",
                ),
            ],
        )

    try:
        content = read_file_safe(file_path)
        all_lines = content.split("\n")
        total = len(all_lines)

        # Determine read range
        s = max(1, start_line if start_line is not None else 1)
        e = min(total, end_line if end_line is not None else total)

        if s > total:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: start_line {s} exceeds file length ({total} lines).",
                    ),
                ],
            )

        if s > e:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: start_line ({s}) > end_line ({e}).",
                    ),
                ],
            )

        # Extract selected lines
        selected_content = "\n".join(all_lines[s - 1 : e])

        # Apply smart truncation (consistent with shell output format)
        file_read_max_bytes = get_current_file_read_max_bytes()
        if file_read_max_bytes is not None:
            max_bytes = file_read_max_bytes
        else:
            max_bytes = get_current_recent_max_bytes() or DEFAULT_MAX_BYTES
        text = truncate_text_output(
            selected_content,
            start_line=s,
            total_lines=total,
            file_path=file_path,
            max_bytes=max_bytes,
        )

        # Add continuation hint if partial read without truncation.
        # Use TRUNCATION_NOTICE_MARKER format so ToolResultCompactor can
        # re-truncate with the correct start_line when compacting old messages.
        if text == selected_content and e < total:
            content_bytes = len(text.encode("utf-8"))
            notice = (
                TRUNCATION_NOTICE_MARKER + f"\nThe output above was truncated."
                f"\nThe full content is saved to the file "
                f"and contains {total} lines in total."
                f"\nThis excerpt starts at line {s} and "
                f"covers the next {content_bytes} bytes."
                "\nIf the current content is not enough, "
                f"call `read_file` with file_path={file_path} "
                f"start_line={e + 1} to read more."
            )
            text = text + notice

        return ToolResponse(
            content=[TextBlock(type="text", text=text)],
        )

    except Exception as e:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: Read file failed due to \n{e}",
                ),
            ],
        )


async def write_file(
    file_path: str,
    content: str,
) -> ToolResponse:
    """Create or overwrite a file. Relative paths resolve from the current agent
    workspace when available, otherwise the current tenant workspace root.

    Args:
        file_path (`str`):
            Path to the file.
        content (`str`):
            Content to write.
    """

    if not file_path:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text="Error: No `file_path` provided.",
                ),
            ],
        )

    # Validate path against tenant boundary
    resolve_started_at = time.perf_counter()
    try:
        file_path = _resolve_writable_file_path(file_path)
    except TenantPathBoundaryError:
        return ToolResponse(
            content=[
                TextBlock(**make_permission_denied_response("Write file")),
            ],
        )
    resolve_seconds = time.perf_counter() - resolve_started_at

    encoding = _get_encoding_for_file(file_path)

    try:
        await _write_file_atomically_with_diagnostics(
            operation="write_file",
            file_path=file_path,
            content=content,
            encoding=encoding,
            resolve_seconds=resolve_seconds,
        )
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Wrote {len(content)} bytes to {file_path}.",
                ),
            ],
        )
    except Exception as e:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: Write file failed due to \n{e}",
                ),
            ],
        )


# pylint: disable=too-many-return-statements
async def edit_file(
    file_path: str,
    old_text: str,
    new_text: str,
) -> ToolResponse:
    """Find-and-replace text in a file. All occurrences of old_text are
    replaced with new_text. Relative paths resolve from the current tenant workspace.

    Args:
        file_path (`str`):
            Path to the file.
        old_text (`str`):
            Exact text to find.
        new_text (`str`):
            Replacement text.
    """

    if not file_path:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text="Error: No `file_path` provided.",
                ),
            ],
        )

    # Validate path against tenant boundary
    try:
        resolved_path = _resolve_file_path(file_path)
    except TenantPathBoundaryError:
        return ToolResponse(
            content=[
                TextBlock(**make_permission_denied_response("Edit file")),
            ],
        )

    if not os.path.exists(resolved_path):
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: The file {resolved_path} does not exist.",
                ),
            ],
        )

    if not os.path.isfile(resolved_path):
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: The path {resolved_path} is not a file.",
                ),
            ],
        )

    try:
        content = read_file_safe(resolved_path)
    except Exception as e:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: Read file failed due to \n{e}",
                ),
            ],
        )

    if old_text not in content:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: The text to replace was not found in {file_path}.",
                ),
            ],
        )

    new_content = content.replace(old_text, new_text)
    write_response = await write_file(
        file_path=resolved_path,
        content=new_content,
    )

    if write_response.content and len(write_response.content) > 0:
        write_text = write_response.content[0].get("text", "")
        if write_text.startswith("Error:"):
            return write_response

    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=f"Successfully replaced text in {file_path}.",
            ),
        ],
    )


async def append_file(
    file_path: str,
    content: str,
) -> ToolResponse:
    """Append content to the end of a file. Relative paths resolve from
    the current agent workspace when available, otherwise the current tenant
    workspace root.

    Args:
        file_path (`str`):
            Path to the file.
        content (`str`):
            Content to append.
    """

    if not file_path:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text="Error: No `file_path` provided.",
                ),
            ],
        )

    # Validate path against tenant boundary
    resolve_started_at = time.perf_counter()
    try:
        file_path = _resolve_writable_file_path(file_path)
    except TenantPathBoundaryError:
        return ToolResponse(
            content=[
                TextBlock(**make_permission_denied_response("Append file")),
            ],
        )
    resolve_seconds = time.perf_counter() - resolve_started_at

    encoding = _get_encoding_for_file(file_path)

    try:
        await _append_file_atomically_with_diagnostics(
            file_path=file_path,
            content=content,
            encoding=encoding,
            resolve_seconds=resolve_seconds,
        )
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Appended {len(content)} bytes to {file_path}.",
                ),
            ],
        )
    except Exception as e:
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: Append file failed due to \n{e}",
                ),
            ],
        )
