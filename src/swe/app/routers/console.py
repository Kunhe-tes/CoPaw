# -*- coding: utf-8 -*-
"""Console APIs: push messages, chat, and file upload for chat."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Literal, Union, Any, Optional, Dict
from urllib.parse import quote

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from agentscope_runtime.engine.schemas.agent_schemas import AgentRequest
from ..agent_context import (
    get_agent_and_config_for_request,
    get_agent_for_request,
)
from ..context_references import (
    ContextReferencesResponse,
    context_reference_directory,
)
from ..file_manager import (
    FileManagerConflictError,
    FileManagerDirectoryListing,
    FileManagerItem,
    FileManagerNotFoundError,
    FileManagerPathError,
    FileManagerTextPreview,
    get_file_manager_service,
)
from ...config.context import resolve_request_effective_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/console", tags=["console"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
DENIED_CHAT_ATTACHMENT_EXECUTABLE_EXTENSIONS = frozenset(
    {
        ".py",
        ".pyw",
        ".java",
        ".class",
        ".jar",
        ".js",
        ".mjs",
        ".cjs",
        ".jsx",
        ".ts",
        ".tsx",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".ps1",
        ".bat",
        ".cmd",
        ".php",
        ".rb",
        ".pl",
        ".lua",
        ".go",
        ".rs",
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".h",
        ".hpp",
        ".cs",
        ".kt",
        ".kts",
        ".swift",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
    },
)
_RECONNECT_ATTACH_ATTEMPTS = 10
_RECONNECT_ATTACH_RETRY_DELAY_SECONDS = 0.1
_CONSOLE_SSE_HEARTBEAT_SECONDS = 15
_B3_TRACE_ID_HEADER = "X-B3-Traceid"
_CHAT_FILE_LIST_LIMIT = 500
_TEXT_SNIFF_BYTES = 4096
_TEXT_PREVIEW_MIME_PREFIX = "text/"
_TEXT_PREVIEW_MIME_TYPES = {
    "application/json",
    "application/xml",
    "application/x-yaml",
    "application/toml",
}
PreviewType = Literal[
    "image",
    "video",
    "audio",
    "office",
    "pdf",
    "markdown",
    "text",
    "html",
    "other",
]
_PREVIEW_TYPES: tuple[PreviewType, ...] = (
    "image",
    "video",
    "audio",
    "office",
    "pdf",
    "markdown",
    "text",
    "html",
    "other",
)
_PREVIEW_TYPE_BY_EXTENSION: dict[str, PreviewType] = {
    **dict.fromkeys(
        ("png", "jpg", "jpeg", "gif", "bmp", "webp", "svg"),
        "image",
    ),
    **dict.fromkeys(
        ("mp4", "avi", "mov", "wmv", "flv", "mkv", "webm"),
        "video",
    ),
    **dict.fromkeys(
        ("mp3", "wav", "flac", "ape", "aac", "ogg", "m4a"),
        "audio",
    ),
    **dict.fromkeys(("doc", "docx", "xls", "xlsx", "ppt", "pptx"), "office"),
    "pdf": "pdf",
    "md": "markdown",
    "mdx": "markdown",
    "html": "html",
    "htm": "html",
    "xhtml": "html",
    **dict.fromkeys(
        (
            "txt",
            "json",
            "xml",
            "csv",
            "log",
            "yaml",
            "yml",
            "toml",
            "ini",
            "conf",
            "config",
            "env",
            "sh",
            "bash",
            "zsh",
            "ps1",
            "bat",
            "cmd",
        ),
        "text",
    ),
}
_PREVIEW_TYPE_BY_MIME: dict[str, PreviewType] = {
    "application/pdf": "pdf",
    "text/html": "html",
    "application/xhtml+xml": "html",
}


def _request_runtime_tenant_id(request: Request) -> str | None:
    """优先返回请求已解析的 runtime scope，避免回退到逻辑 tenant。"""
    return resolve_request_effective_tenant_id(
        getattr(request.state, "tenant_id", None),
        getattr(request.state, "source_id", None),
        getattr(request.state, "scope_id", None),
    )


_PREVIEW_MIME_PREFIXES: tuple[tuple[str, PreviewType], ...] = (
    ("image/", "image"),
    ("video/", "video"),
    ("audio/", "audio"),
)
_UPLOADED_STORED_NAME_PATTERN = re.compile(r"^[0-9a-f]{32}_(?P<name>.+)$")


class GeneratedFileItem(BaseModel):
    """聊天相关文件列表项。"""

    name: str = Field(..., description="文件名")
    display_name: str = Field(..., description="用于界面展示的文件名")
    relative_path: str = Field(..., description="相对来源目录的路径")
    file_url: str = Field(..., description="文件绝对路径")
    size: int = Field(..., description="文件大小，单位字节")
    modified_at: str = Field(..., description="最后修改时间")
    mime_type: str | None = Field(default=None, description="文件 MIME 类型")
    preview_type: Literal[
        "image",
        "video",
        "audio",
        "office",
        "pdf",
        "markdown",
        "text",
        "html",
        "other",
    ] = Field(default="other", description="前端预览类型")
    source: Literal["generated", "uploaded"] = Field(
        ...,
        description="文件来源：generated 表示生成文件，uploaded 表示上传文件",
    )


class GeneratedFilesResponse(BaseModel):
    """聊天相关文件列表响应。"""

    files: list[GeneratedFileItem] = Field(default_factory=list)


def _file_manager_http_error(error: FileManagerPathError) -> HTTPException:
    """Map controlled filesystem errors without revealing host paths."""

    if isinstance(error, FileManagerNotFoundError):
        return HTTPException(
            status_code=404,
            detail="File manager item not found",
        )
    if isinstance(error, FileManagerConflictError):
        return HTTPException(status_code=409, detail=str(error))
    return HTTPException(status_code=403, detail=str(error))


class FileManagerTextSaveRequest(BaseModel):
    root: str
    path: str
    content: str
    revision: str


def _file_manager_actor(request: Request) -> str:
    """Return a bounded audit actor without depending on one auth scheme."""

    for candidate in (
        request.headers.get("X-Actor"),
        request.headers.get("X-User-Id"),
        getattr(request.state, "actor", None),
        getattr(request.state, "user_id", None),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()[:256]
    return "unknown"


def _audit_file_manager_mutation(
    request: Request,
    *,
    action: str,
    path: str,
    outcome: str,
) -> None:
    """Best-effort mutation audit; never include or log file contents."""

    try:
        logger.info(
            "file_manager.audit",
            extra={
                "actor": _file_manager_actor(request),
                "time": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "path": path,
                "outcome": outcome,
            },
        )
    except Exception:
        # Audit delivery must not turn a successful filesystem mutation into a
        # request failure.
        pass


def _file_manager_upload_audit_path(directory: str, filename: str) -> str:
    """Keep early upload-rejection audit paths bounded and path-shaped."""

    safe_filename = _safe_filename(filename or "file")
    safe_parts = [
        part
        for part in directory.split("/")
        if part not in {"", ".", ".."}
        and "\\" not in part
        and "\x00" not in part
    ]
    return "/".join([*safe_parts, safe_filename])


def _file_manager_download_disposition(filename: str) -> str:
    """Create a header-safe attachment filename without leaking a path."""

    if (
        filename.isascii()
        and all(32 <= ord(character) <= 126 for character in filename)
        and '"' not in filename
        and "\\" not in filename
    ):
        return f'attachment; filename="{filename}"'
    return f"attachment; filename*=UTF-8''{quote(filename, safe='')}"


class _FileManagerDownloadStream:
    """A bounded, idempotently-closeable streaming download descriptor."""

    def __init__(self, file_descriptor: int, size_bytes: int) -> None:
        self._file_descriptor: int | None = file_descriptor
        self._remaining = size_bytes

    def __iter__(self):
        return self

    def __next__(self) -> bytes:
        if self._file_descriptor is None or self._remaining <= 0:
            self.close()
            raise StopIteration
        try:
            chunk = os.read(
                self._file_descriptor,
                min(64 * 1024, self._remaining),
            )
        except OSError:
            self.close()
            raise
        if not chunk:
            self.close()
            raise StopIteration
        self._remaining -= len(chunk)
        if self._remaining == 0:
            self.close()
        return chunk

    def close(self) -> None:
        """Release the descriptor even when a response never starts streaming."""

        file_descriptor, self._file_descriptor = self._file_descriptor, None
        if file_descriptor is None:
            return
        try:
            os.close(file_descriptor)
        except OSError:
            # A cancelled stream or a completed iterator may already close it.
            pass


class _FileManagerDownloadResponse(StreamingResponse):
    """A download response that closes its descriptor on every exit path."""

    def __init__(
        self,
        stream: _FileManagerDownloadStream,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._file_manager_stream = stream
        super().__init__(
            stream,
            media_type="application/octet-stream",
            headers=headers,
        )

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._file_manager_stream.close()


def _looks_like_text_file(path: Path) -> bool:
    """在缺少后缀时通过内容嗅探判断是否可按文本预览。"""
    try:
        sample = path.read_bytes()[:_TEXT_SNIFF_BYTES]
    except OSError:
        return False
    if not sample:
        return True
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _resolve_display_name(
    file_name: str,
    source: Literal["generated", "uploaded"],
) -> str:
    """上传文件展示原始文件名，生成文件展示实际文件名。"""
    if source != "uploaded":
        return file_name
    match = _UPLOADED_STORED_NAME_PATTERN.match(file_name)
    if not match:
        return file_name
    return match.group("name") or file_name


def _resolve_preview_type_from_mime(
    mime_type: str | None,
) -> PreviewType | None:
    """在后缀无法判断时，根据 MIME 推断前端预览类型。"""
    if not mime_type:
        return None

    for prefix, preview_type in _PREVIEW_MIME_PREFIXES:
        if mime_type.startswith(prefix):
            return preview_type

    preview_type = _PREVIEW_TYPE_BY_MIME.get(mime_type)
    if preview_type is not None:
        return preview_type

    if (
        mime_type.startswith(_TEXT_PREVIEW_MIME_PREFIX)
        or mime_type in _TEXT_PREVIEW_MIME_TYPES
    ):
        return "text"
    return None


def _resolve_preview_type(
    path: Path,
    mime_type: str | None,
) -> PreviewType:
    """根据后缀、MIME 与内容嗅探给前端提供稳定预览类型。"""
    ext = path.suffix.lower().lstrip(".")
    preview_type = _PREVIEW_TYPE_BY_EXTENSION.get(ext)
    if preview_type is not None:
        return preview_type

    preview_type = _resolve_preview_type_from_mime(mime_type)
    if preview_type is not None:
        return preview_type

    if _looks_like_text_file(path):
        return "text"
    return "other"


def _collect_chat_files_from_dir(
    root_dir: Path,
    source: Literal["generated", "uploaded"],
) -> list[GeneratedFileItem]:
    """从指定目录收集聊天文件，并限制路径只来自该目录内部。"""
    if not root_dir.is_dir():
        return []

    items: list[GeneratedFileItem] = []
    for path in root_dir.rglob("*"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        try:
            relative_path = resolved.relative_to(root_dir).as_posix()
        except ValueError:
            continue
        stat = resolved.stat()
        mime_type, _ = mimetypes.guess_type(str(resolved))
        items.append(
            GeneratedFileItem(
                name=resolved.name,
                display_name=_resolve_display_name(resolved.name, source),
                relative_path=relative_path,
                file_url=str(resolved),
                size=stat.st_size,
                modified_at=datetime.fromtimestamp(
                    stat.st_mtime,
                ).isoformat(),
                mime_type=mime_type,
                preview_type=_resolve_preview_type(resolved, mime_type),
                source=source,
            ),
        )
    return items


async def _resolve_console_media_dir(workspace, workspace_dir: Path) -> Path:
    """解析 Console 上传目录，保持文件列表与上传接口使用同一位置。"""
    channel_manager = getattr(workspace, "channel_manager", None)
    if channel_manager is not None:
        console_channel = await channel_manager.get_channel("console")
        media_dir = getattr(console_channel, "media_dir", None)
        if media_dir:
            return Path(media_dir).expanduser().resolve()
    return (workspace_dir / "media").resolve()


async def _stream_with_keepalive(
    source: AsyncGenerator[str, None],
    interval: float = _CONSOLE_SSE_HEARTBEAT_SECONDS,
) -> AsyncGenerator[str, None]:
    """Wrap an SSE generator with keepalive comment frames.

    When no real event arrives within *interval* seconds, emits an SSE
    comment line ``: keep-alive\\n\\n`` which is ignored by EventSource
    but keeps reverse proxies (nginx, ALB) from closing the connection
    due to idle timeout.
    """

    async def _next_item(
        it: AsyncGenerator[str, None],
    ) -> tuple[str, bool]:
        """Return (event, True) or ('', False) when the iterator is done."""
        try:
            return await it.__anext__(), True
        except StopAsyncIteration:
            return "", False

    pending = asyncio.ensure_future(_next_item(source))
    try:
        while True:
            done, _ = await asyncio.wait(
                (pending,),
                timeout=interval,
            )
            if done:
                event_data, has_more = pending.result()
                if not has_more:
                    return
                yield event_data
                pending = asyncio.ensure_future(_next_item(source))
            else:
                # No real event within interval — send keepalive
                yield ": keep-alive\n\n"
    finally:
        pending.cancel()
        try:
            await pending
        except (asyncio.CancelledError, StopAsyncIteration):
            pass


def _safe_filename(name: str) -> str:
    """Safe basename, alphanumeric/./-/_, max 200 chars."""
    base = Path(name).name if name else "file"
    return re.sub(r"[^\w.\-]", "_", base)[:200] or "file"


def _has_denied_chat_attachment_extension(filename: str | None) -> bool:
    """Return True when the outer filename extension is denied."""
    suffix = Path(filename or "").suffix.lower()
    return suffix in DENIED_CHAT_ATTACHMENT_EXECUTABLE_EXTENSIONS


def _extract_content_parts_from_mapping(request_data: dict) -> list[Any]:
    """从 dict 形态请求中提取完整 content parts。"""
    input_data = request_data.get("input", [])
    content_parts: list[Any] = []
    for content_part in input_data:
        if hasattr(content_part, "content"):
            content_parts.extend(list(content_part.content or []))
            continue
        if isinstance(content_part, dict) and "content" in content_part:
            content_parts.extend(content_part.get("content") or [])
    return content_parts


def _extract_payload_fields_from_request(
    request_data: AgentRequest,
) -> tuple[str, str, str, Any, Any, Any, Any, Any, list[Any]]:
    """提取 AgentRequest 形态请求的核心字段。"""
    channel_meta = getattr(request_data, "channel_meta", None) or {}
    selected_skill_names = getattr(
        request_data,
        "selected_skill_names",
        None,
    )
    if selected_skill_names is None:
        selected_skill_names = channel_meta.get("selected_skill_names")
    return (
        getattr(request_data, "channel", None) or "console",
        request_data.user_id or "default",
        request_data.session_id or "default",
        getattr(request_data, "user_name", None)
        or channel_meta.get("user_name"),
        getattr(request_data, "bbk_id", None) or channel_meta.get("bbk_id"),
        getattr(request_data, "system_prompt_injections", None),
        getattr(request_data, "file_url_network", None),
        selected_skill_names,
        list(request_data.input[0].content) if request_data.input else [],
    )


def _extract_payload_fields_from_mapping(
    request_data: dict,
) -> tuple[str, str, str, Any, Any, Any, Any, Any, list[Any]]:
    """提取 dict 形态请求的核心字段。"""
    return (
        request_data.get("channel", "console"),
        request_data.get("user_id", "default"),
        request_data.get("session_id", "default"),
        request_data.get("user_name"),
        request_data.get("bbk_id"),
        request_data.get("system_prompt_injections"),
        request_data.get("file_url_network"),
        request_data.get("selected_skill_names"),
        _extract_content_parts_from_mapping(request_data),
    )


def _extract_context_references(
    request_data: Union[AgentRequest, dict],
) -> Any:
    """Keep structured one-turn context references intact for the runner."""
    if isinstance(request_data, AgentRequest):
        channel_meta = getattr(request_data, "channel_meta", None) or {}
        value = getattr(request_data, "context_references", None)
        if value is None and isinstance(channel_meta, dict):
            value = channel_meta.get("context_references")
        return value
    return request_data.get("context_references")


def _extract_session_and_payload(request_data: Union[AgentRequest, dict]):
    """Extract run_key (ChatSpec.id), session_id, and native payload.

    Align with qwenpaw: keep full multimodal content parts (text/file/image/audio/video)
    instead of dropping non-text blocks.

    run_key must be ChatSpec.id (chat_id) so it matches list_chats/get_chat.
    """
    if isinstance(request_data, AgentRequest):
        (
            _channel_id,
            sender_id,
            session_id,
            user_name,
            bbk_id,
            system_prompt_injections,
            file_url_network,
            selected_skill_names,
            content_parts,
        ) = _extract_payload_fields_from_request(request_data)
    else:
        (
            _channel_id,
            sender_id,
            session_id,
            user_name,
            bbk_id,
            system_prompt_injections,
            file_url_network,
            selected_skill_names,
            content_parts,
        ) = _extract_payload_fields_from_mapping(request_data)

    native_payload: dict[str, Any] = {
        # /console/chat always executes through the Console runtime.  Do not
        # trust the client-provided channel when resolving effective skills.
        "channel_id": "console",
        "sender_id": sender_id,
        "content_parts": content_parts,
        "meta": {
            "session_id": session_id,
            "user_id": sender_id,
        },
    }
    if system_prompt_injections is not None:
        native_payload["meta"][
            "system_prompt_injections"
        ] = system_prompt_injections
    if file_url_network is not None:
        native_payload["meta"]["file_url_network"] = file_url_network
    if selected_skill_names is not None:
        native_payload["meta"]["selected_skill_names"] = selected_skill_names
    context_references = _extract_context_references(request_data)
    if context_references is not None:
        native_payload["meta"]["context_references"] = context_references
    if user_name:
        native_payload["meta"]["user_name"] = user_name
    if bbk_id:
        native_payload["meta"]["bbk_id"] = bbk_id
    return native_payload


def _derive_chat_name(native_payload: dict) -> str:
    """Build a display name for a newly created chat."""
    if not native_payload["content_parts"]:
        return "New Chat"

    content = native_payload["content_parts"][0]
    if not content:
        return "Media Message"
    if isinstance(content, dict):
        return content.get("text", "New Chat")[:10]
    if hasattr(content, "text"):
        return content.text[:10]
    return "Media Message"


def _extract_b3_trace_id(request: Request) -> str | None:
    trace_id = request.headers.get(_B3_TRACE_ID_HEADER)
    if trace_id is None:
        return None
    trace_id = trace_id.strip()
    return trace_id or None


async def _attach_reconnect_queue(
    workspace,
    tracker,
    session_id: str,
    channel_id: str,
) -> tuple[asyncio.Queue, str]:
    """Attach to a running chat by chat_id or logical session_id."""
    for attempt in range(_RECONNECT_ATTACH_ATTEMPTS):
        chat = await workspace.chat_manager.get_chat(session_id)
        if chat is not None:
            queue = await tracker.attach(chat.id)
            if queue is not None:
                return queue, chat.id

        chat_id = await workspace.chat_manager.get_chat_id_by_session(
            session_id,
            channel_id,
        )
        if chat_id is not None:
            queue = await tracker.attach(chat_id)
            if queue is not None:
                return queue, chat_id

        if attempt < _RECONNECT_ATTACH_ATTEMPTS - 1:
            await asyncio.sleep(_RECONNECT_ATTACH_RETRY_DELAY_SECONDS)

    raise HTTPException(
        status_code=404,
        detail="No running chat for this session",
    )


def _console_chat_stream_headers(
    *,
    session_id: str,
    msgid: str | None,
) -> dict[str, str]:
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    if msgid:
        headers["X-Swe-Msgid"] = msgid
        headers["X-Swe-Sessionid"] = session_id
    return headers


async def _start_new_chat(
    workspace,
    tracker,
    console_channel,
    session_id,
    native_payload,
):
    """创建新会话并启动 stream，返回 (queue, run_key, msgid)。"""
    msgid = str(uuid.uuid4())
    native_payload["meta"]["msgid"] = msgid
    chat = await workspace.chat_manager.get_or_create_chat(
        session_id,
        native_payload["sender_id"],
        native_payload["channel_id"],
        name=_derive_chat_name(native_payload),
        meta=(
            {
                "agent_id": workspace.agent_id,
            }
            if getattr(workspace, "agent_id", None)
            else None
        ),
    )
    # Inject session_channel from chat record so downstream (e.g. session-end
    # push) can identify the session's original channel (e.g. zhaohu).
    if chat.channel and chat.channel != "console":
        native_payload["meta"]["session_channel"] = chat.channel
    queue, _ = await tracker.attach_or_start(
        chat.id,
        native_payload,
        console_channel.stream_one,
    )
    return queue, chat.id, msgid


@router.post(
    "/chat",
    status_code=200,
    summary="Chat with console (streaming response)",
    description="Agent API Request Format. See runtime.agentscope.io. "
    "Use body.reconnect=true to attach to a running stream.",
)
async def post_console_chat(
    request_data: Union[AgentRequest, dict],
    request: Request,
) -> StreamingResponse:
    """Stream agent response. Run continues in background after disconnect.
    Stop via POST /console/chat/stop. Reconnect with body.reconnect=true.
    """
    workspace = await get_agent_for_request(request)
    console_channel = await workspace.channel_manager.get_channel("console")
    if console_channel is None:
        raise HTTPException(
            status_code=503,
            detail="Channel Console not found",
        )
    try:
        native_payload = _extract_session_and_payload(request_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    b3_trace_id = _extract_b3_trace_id(request)
    if b3_trace_id:
        native_payload["meta"]["b3_trace_id"] = b3_trace_id

    # Inject source_id from resolved request state for data isolation
    source_id = getattr(
        request.state,
        "source_id",
        None,
    ) or request.headers.get(
        "X-Source-Id",
    )
    if not source_id:
        raise HTTPException(
            status_code=400,
            detail="X-Source-Id header is required",
        )
    native_payload["meta"]["source_id"] = source_id

    # 从 request.state 获取 user_name 和 bbk_id（由 TenantIdentityMiddleware 设置）
    request_state = getattr(request, "state", None)
    if request_state:
        user_name = getattr(request_state, "user_name", None)
        bbk_id = getattr(request_state, "bbk_id", None)
        if user_name:
            native_payload["meta"]["user_name"] = user_name
        if bbk_id:
            native_payload["meta"]["bbk_id"] = bbk_id

    # Debug: log the session_id from frontend
    logger.debug(
        "Console chat: native_payload.meta.session_id=%s",
        native_payload.get("meta", {}).get("session_id"),
    )
    session_id = console_channel.resolve_session_id(
        sender_id=native_payload["sender_id"],
        channel_meta=native_payload["meta"],
    )
    logger.debug(
        "Console chat: resolved session_id=%s",
        session_id,
    )
    tracker = workspace.task_tracker

    is_reconnect = False
    if isinstance(request_data, dict):
        is_reconnect = request_data.get("reconnect") is True

    msgid: str | None = None
    if is_reconnect:
        queue, run_key = await _attach_reconnect_queue(
            workspace,
            tracker,
            session_id,
            native_payload["channel_id"],
        )
        if queue is None:
            raise HTTPException(
                status_code=404,
                detail="No running chat for this session",
            )
    else:
        queue, run_key, msgid = await _start_new_chat(
            workspace,
            tracker,
            console_channel,
            session_id,
            native_payload,
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        # Hold iterator so finally can aclose(); guarantees stream_from_queue's
        # finally (detach_subscriber) on client abort / generator teardown.
        stream_it = tracker.stream_from_queue(queue, run_key)
        yield ": keep-alive\n\n"
        try:
            try:
                async for event_data in stream_it:
                    yield event_data
            except Exception as e:
                logger.exception("Console chat stream error")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            await stream_it.aclose()

    return StreamingResponse(
        _stream_with_keepalive(event_generator()),
        media_type="text/event-stream",
        headers=_console_chat_stream_headers(
            session_id=session_id,
            msgid=msgid,
        ),
    )


@router.post(
    "/chat/stop",
    status_code=200,
    summary="Stop running console chat",
)
async def post_console_chat_stop(
    request: Request,
    chat_id: str = Query(..., description="Chat id (ChatSpec.id) to stop"),
) -> dict:
    """Stop the running chat. Only stops when called."""
    workspace = await get_agent_for_request(request)
    stopped = await workspace.task_tracker.request_stop(chat_id)
    return {"stopped": stopped}


@router.post("/upload", response_model=dict, summary="Upload file for chat")
async def post_console_upload(
    request: Request,
    file: UploadFile = File(..., description="File to attach"),
) -> dict:
    """Save to console channel media_dir."""

    if _has_denied_chat_attachment_extension(file.filename):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type for chat attachment upload",
        )

    workspace = await get_agent_for_request(request)
    console_channel = await workspace.channel_manager.get_channel("console")
    if console_channel is None:
        raise HTTPException(
            status_code=503,
            detail="Channel Console not found",
        )
    media_dir = console_channel.media_dir
    media_dir.mkdir(parents=True, exist_ok=True)
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail="File too large (max "
            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )
    safe_name = _safe_filename(file.filename or "file")
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"

    path = (media_dir / stored_name).resolve()
    path.write_bytes(data)
    return {
        "url": path,
        "file_name": safe_name,
        "size": len(data),
    }


@router.get(
    "/generated-files",
    response_model=GeneratedFilesResponse,
    summary="列出当前聊天工作区相关文件",
)
async def get_console_generated_files(
    request: Request,
    sort: str = Query(
        "desc",
        pattern="^(asc|desc)$",
        description="按修改时间排序：asc 或 desc",
    ),
    source: str = Query(
        "all",
        pattern="^(all|generated|uploaded)$",
        description="文件来源：all、generated 或 uploaded",
    ),
) -> GeneratedFilesResponse:
    """列出当前 Agent 工作区 static 与 media 目录下的聊天相关文件。"""
    workspace = await get_agent_for_request(request)
    workspace_dir = Path(workspace.workspace_dir)
    items: list[GeneratedFileItem] = []
    if source in ("all", "generated"):
        items.extend(
            _collect_chat_files_from_dir(
                (workspace_dir / "static").resolve(),
                "generated",
            ),
        )
    if source in ("all", "uploaded"):
        media_dir = await _resolve_console_media_dir(
            workspace,
            workspace_dir,
        )
        items.extend(
            _collect_chat_files_from_dir(
                media_dir,
                "uploaded",
            ),
        )

    reverse = sort != "asc"
    items.sort(key=lambda item: item.modified_at, reverse=reverse)
    return GeneratedFilesResponse(
        files=items[:_CHAT_FILE_LIST_LIMIT],
    )


@router.get(
    "/file-manager/directories",
    response_model=FileManagerDirectoryListing,
    summary="List a controlled chat file-manager directory",
)
async def get_file_manager_directory(
    request: Request,
    root: str = Query(..., description="Controlled file-manager root"),
    path: str = Query("", description="Relative POSIX directory path"),
    cursor: str | None = Query(None, description="Signed directory cursor"),
    q: str = Query("", max_length=512, description="Direct-child name filter"),
) -> FileManagerDirectoryListing:
    """List direct children for the workspace bound to this request only."""

    workspace = await get_agent_for_request(request)
    service = get_file_manager_service(Path(workspace.workspace_dir))
    try:
        return service.list_directory(
            root,
            path,
            cursor=cursor,
            query=q or None,
        )
    except FileManagerPathError as exc:
        raise _file_manager_http_error(exc) from exc


@router.get(
    "/file-manager/files/read",
    response_model=FileManagerTextPreview,
    summary="Read a bounded controlled text-file preview",
)
async def get_file_manager_file_preview(
    request: Request,
    root: str = Query(..., description="Controlled file-manager root"),
    path: str = Query(..., description="Relative POSIX file path"),
) -> FileManagerTextPreview:
    """Return at most one MiB of UTF-8 text without auditing reads."""

    workspace = await get_agent_for_request(request)
    service = get_file_manager_service(Path(workspace.workspace_dir))
    try:
        return service.read_text_preview(root, path)
    except FileManagerPathError as exc:
        raise _file_manager_http_error(exc) from exc


@router.get(
    "/file-manager/files/download",
    summary="Download one controlled regular file as an attachment",
)
async def get_file_manager_file_download(
    request: Request,
    root: str = Query(..., description="Controlled file-manager root"),
    path: str = Query(..., description="Relative POSIX file path"),
) -> StreamingResponse:
    """Stream a single regular file from a no-follow descriptor, unaudited."""

    workspace = await get_agent_for_request(request)
    service = get_file_manager_service(Path(workspace.workspace_dir))
    try:
        download = service.open_file_for_download(root, path)
    except FileManagerPathError as exc:
        raise _file_manager_http_error(exc) from exc
    stream = _FileManagerDownloadStream(
        download.file_descriptor,
        download.size_bytes,
    )
    return _FileManagerDownloadResponse(
        stream,
        headers={
            "Content-Disposition": _file_manager_download_disposition(
                download.filename,
            ),
        },
    )


@router.put(
    "/file-manager/files/text",
    response_model=FileManagerTextPreview,
    summary="Save one revision-checked controlled text file",
)
async def put_file_manager_text_file(
    request: Request,
    body: FileManagerTextSaveRequest,
) -> FileManagerTextPreview:
    """Save small UTF-8 text only, rejecting stale revisions instead of overwrite."""

    workspace = await get_agent_for_request(request)
    service = get_file_manager_service(Path(workspace.workspace_dir))
    try:
        result = service.save_text(
            body.root,
            body.path,
            body.content,
            body.revision,
        )
    except FileManagerPathError as exc:
        _audit_file_manager_mutation(
            request,
            action="save",
            path=body.path,
            outcome="failure",
        )
        raise _file_manager_http_error(exc) from exc
    _audit_file_manager_mutation(
        request,
        action="save",
        path=body.path,
        outcome="success",
    )
    return result


@router.post(
    "/file-manager/files/upload",
    response_model=FileManagerItem,
    summary="Upload a new controlled file without replacing an existing name",
)
async def post_file_manager_upload(
    request: Request,
    file: UploadFile = File(..., description="File to upload"),
    root: str = Query(..., description="Controlled file-manager root"),
    path: str = Query(
        "",
        description="Existing relative destination directory",
    ),
) -> FileManagerItem:
    """Upload to the currently browsed directory, never renaming or replacing."""

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        _audit_file_manager_mutation(
            request,
            action="upload",
            path=_file_manager_upload_audit_path(path, file.filename or ""),
            outcome="failure",
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)"
            ),
        )
    workspace = await get_agent_for_request(request)
    service = get_file_manager_service(Path(workspace.workspace_dir))
    filename = file.filename or ""
    try:
        item = service.upload_bytes(root, path, filename, content)
    except FileManagerPathError as exc:
        _audit_file_manager_mutation(
            request,
            action="upload",
            path=path,
            outcome="failure",
        )
        raise _file_manager_http_error(exc) from exc
    _audit_file_manager_mutation(
        request,
        action="upload",
        path=item.path,
        outcome="success",
    )
    return item


@router.delete(
    "/file-manager/files",
    summary="Recoverably archive one controlled regular file",
)
async def delete_file_manager_file(
    request: Request,
    root: str = Query(..., description="Controlled file-manager root"),
    path: str = Query(..., description="Relative regular file path"),
) -> dict[str, str]:
    """Move a file-manager file into the governance recycle-bin archive."""

    workspace = await get_agent_for_request(request)
    service = get_file_manager_service(Path(workspace.workspace_dir))
    try:
        archived = service.archive_file(
            root,
            path,
            actor=_file_manager_actor(request),
        )
    except FileManagerPathError as exc:
        _audit_file_manager_mutation(
            request,
            action="archive",
            path=path,
            outcome="failure",
        )
        raise _file_manager_http_error(exc) from exc
    _audit_file_manager_mutation(
        request,
        action="archive",
        path=archived.original_path,
        outcome="success",
    )
    return {
        "archive_item_id": archived.archive_item_id,
        "original_path": archived.original_path,
    }


@router.post(
    "/file-manager/recycle/{archive_item_id}/restore",
    summary="Restore one recycle item to its original path without overwrite",
)
async def post_file_manager_recycle_restore(
    request: Request,
    archive_item_id: str,
) -> dict[str, str]:
    """Restore one archive item; a collision leaves the archive untouched."""

    workspace = await get_agent_for_request(request)
    service = get_file_manager_service(Path(workspace.workspace_dir))
    try:
        restored = service.restore_recycle_item(
            archive_item_id,
            actor=_file_manager_actor(request),
        )
    except FileManagerPathError as exc:
        _audit_file_manager_mutation(
            request,
            action="restore",
            path=archive_item_id,
            outcome="failure",
        )
        raise _file_manager_http_error(exc) from exc
    _audit_file_manager_mutation(
        request,
        action="restore",
        path=restored.original_path,
        outcome="success",
    )
    return {
        "archive_item_id": restored.archive_item_id,
        "original_path": restored.original_path,
    }


@router.delete(
    "/file-manager/recycle/{archive_item_id}",
    summary="Permanently delete one recycle item",
)
async def delete_file_manager_recycle_item(
    request: Request,
    archive_item_id: str,
) -> dict[str, str]:
    """Remove archived bytes and index entry after the UI confirmation."""

    workspace = await get_agent_for_request(request)
    service = get_file_manager_service(Path(workspace.workspace_dir))
    try:
        purged = service.purge_recycle_item(
            archive_item_id,
            actor=_file_manager_actor(request),
        )
    except FileManagerPathError as exc:
        _audit_file_manager_mutation(
            request,
            action="purge",
            path=archive_item_id,
            outcome="failure",
        )
        raise _file_manager_http_error(exc) from exc
    _audit_file_manager_mutation(
        request,
        action="purge",
        path=purged.original_path,
        outcome="success",
    )
    return {
        "archive_item_id": purged.archive_item_id,
        "original_path": purged.original_path,
    }


@router.get(
    "/context-references",
    response_model=ContextReferencesResponse,
    summary="Discover context references for the Console composer",
)
async def get_context_references(
    request: Request,
    q: str = Query("", max_length=512),
) -> ContextReferencesResponse:
    """Return cached, scope-bound Skills, MCP tools, and matching files."""
    workspace, agent_config = await get_agent_and_config_for_request(request)
    workspace_dir = Path(workspace.workspace_dir)
    return await context_reference_directory.discover(
        workspace=workspace,
        agent_config=agent_config,
        query=q,
        media_dir=await _resolve_console_media_dir(workspace, workspace_dir),
    )


@router.get("/push-messages")
async def get_push_messages(
    request: Request,
    session_id: str | None = Query(None, description="Session id"),
):
    """Return pending push messages for the current tenant session.

    If session_id is provided, returns messages for that specific session.
    If session_id is not provided, returns all messages for the tenant.
    """
    from ..console_push_store import take, take_all

    tenant_id = _request_runtime_tenant_id(request)

    if session_id:
        messages = await take(session_id, tenant_id=tenant_id)
    else:
        messages = await take_all(tenant_id=tenant_id)

    return {"messages": messages}


@router.get("/suggestions")
async def get_suggestions(
    request: Request,
    session_id: str = Query(
        ...,
        description="Session id to get suggestions for",
    ),
):
    """Return generated suggestions for the session.

    猜你想问建议在后台异步生成，前端在主响应完成后轮询此接口获取。
    获取后建议会被移除，不会重复返回。
    """
    from ..suggestions import take_suggestions

    tenant_id = _request_runtime_tenant_id(request)
    suggestions = await take_suggestions(session_id, tenant_id=tenant_id)
    return {"suggestions": suggestions}


class QAContentRequest(BaseModel):
    """Q&A 内容请求模型."""

    chat_id: str = Field(..., description="Chat id (backend chat.id)")
    user_message: str = Field(..., description="User message text")


class QAContentResponse(BaseModel):
    """Q&A 内容响应模型."""

    success: bool = Field(..., description="Whether Q&A content was found")
    qa_content: Optional[Dict[str, str]] = Field(
        default=None,
        description="Extracted Q&A content (user_message, assistant_response)",
    )


@router.post("/suggestions/qa-content", response_model=QAContentResponse)
async def get_suggestions_qa_content(
    request: Request,
    body: QAContentRequest,
):
    """根据用户问题获取后端提取的 Q&A 内容.

    前端在响应完成后调用此接口，获取后端提取的 Q&A 关键内容，
    用于调用外部 suggestions API。

    Args:
        chat_id: 后端 chat.id（UUID）
        user_message: 用户问题文本（用于匹配）

    Returns:
        success: 是否找到 Q&A 内容
        qa_content: 提取后的用户问题和助手回答（总长度不超过配置上限）
    """
    from ..suggestions import get_qa_content

    tenant_id = _request_runtime_tenant_id(request)

    entry = await get_qa_content(
        chat_id=body.chat_id,
        user_message=body.user_message,
        tenant_id=tenant_id,
    )

    if entry is None:
        return QAContentResponse(
            success=False,
            qa_content=None,
        )

    return QAContentResponse(
        success=True,
        qa_content=entry,
    )
