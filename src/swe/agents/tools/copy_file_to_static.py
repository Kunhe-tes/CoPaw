# -*- coding: utf-8 -*-
"""copy file to static folder tool."""

import json
import shutil
import os
from pathlib import Path

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from ..tool_failure import ToolExecutionError
from ...app.agent_context import get_current_agent_id
from ...config.context import (
    get_current_effective_tenant_id,
    get_current_file_url_network,
    get_current_user_id,
    get_current_workspace_dir,
    resolve_file_url_base,
)


def _raise_tool_error(error_type: str, msg: str) -> None:
    raise ToolExecutionError(error_type=error_type, detail=msg)


def _tool_ok(
    path: str,
    message: str,
    *,
    url: str,
    network: str,
) -> ToolResponse:
    """Return success response."""
    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=json.dumps(
                    {
                        "ok": True,
                        "path": path,
                        "url": url,
                        "network": network,
                        "message": message,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ),
        ],
    )


def _find_single_file(directory: Path) -> Path | None:
    files = [path for path in directory.iterdir() if path.is_file()]
    if len(files) == 1:
        return files[0]
    return None


def _find_static_file_by_name(
    static_dir: Path,
    requested_path: Path,
) -> Path | None:
    file_name = requested_path.name
    if not file_name or not static_dir.exists():
        return None

    direct = static_dir / file_name
    if direct.is_file():
        return direct

    matches: list[Path] = []
    for candidate in static_dir.rglob(file_name):
        if candidate.is_file():
            matches.append(candidate)
            if len(matches) > 1:
                return None
    return matches[0] if matches else None


def _resolve_source_file_path(file_path: str, working_dir: Path) -> Path:
    requested_path = Path(file_path).expanduser()
    if not requested_path.is_absolute():
        requested_path = working_dir / requested_path

    if requested_path.exists():
        if requested_path.is_file():
            return requested_path
        single_file = _find_single_file(requested_path)
        if single_file is not None:
            return single_file
        _raise_tool_error(
            "invalid_arguments",
            f"Path is not a file: {requested_path}",
        )

    static_match = _find_static_file_by_name(
        working_dir / "static",
        requested_path,
    )
    if static_match is not None:
        return static_match

    _raise_tool_error("not_found", f"File not found: {requested_path}")


async def copy_file_to_static(file_path: str) -> ToolResponse:
    """copy a file to the static folder under the working directory.

    This tool copys the specified file to the `static` subdirectory of the
    current working directory. If the `static` folder does not exist, it
    will be created automatically.

    Args:
        file_path (`str`):
            The absolute or relative path of the file to copy.

    Returns:
        `ToolResponse`:
            JSON with "ok", a markdown link accessible to the user.
    """
    # Validate input
    if not file_path or not file_path.strip():
        _raise_tool_error("invalid_arguments", "file_path is required")

    file_path = file_path.strip()

    # Get working directory and create static folder if needed
    working_dir = get_current_workspace_dir()
    if working_dir is None:
        _raise_tool_error(
            "unexpected_tool_error",
            "workspace directory is not configured",
        )
    source_path = _resolve_source_file_path(file_path, working_dir)
    static_dir = working_dir / "static"

    try:
        static_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        _raise_tool_error(
            "unexpected_tool_error",
            f"Failed to create static directory: {e!s}",
        )

    # Build destination path
    file_name = source_path.name
    dest_path = static_dir / file_name
    source_resolved = source_path.resolve()
    static_resolved = static_dir.resolve()

    # If the file is already directly exposed from static, return its link.
    if source_resolved.parent == static_resolved:
        dest_path = source_path
    elif dest_path.exists():
        base, ext = os.path.splitext(file_name)
        counter = 1
        while dest_path.exists():
            dest_path = static_dir / f"{base}_{counter}{ext}"
            counter += 1
    if dest_path != source_path:
        try:
            shutil.copy(source_path, dest_path)
        except Exception as e:
            _raise_tool_error(
                "unexpected_tool_error",
                f"Failed to copy file: {e!s}",
            )

    # 静态路由按运行时租户目录取文件，source-scoped 请求不能使用逻辑用户 ID。
    static_scope_id = (
        get_current_effective_tenant_id() or get_current_user_id() or "default"
    )
    file_name = os.path.basename(dest_path)
    agent_id = get_current_agent_id()
    access, network = resolve_file_url_base(get_current_file_url_network())
    url = (
        access
        + "/static/"
        + static_scope_id
        + "/"
        + agent_id
        + "/"
        + file_name
    )

    return _tool_ok(
        f"![{file_name}]({url})",
        "已返回markdown格式的访问链接",
        url=url,
        network=network,
    )
