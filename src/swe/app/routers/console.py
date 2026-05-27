# -*- coding: utf-8 -*-
"""Console APIs: push messages, chat, and file upload for chat."""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Literal, Union, Any, Optional, Dict

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
from ..agent_context import get_agent_for_request
from ...config.context import resolve_scope_preferred_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/console", tags=["console"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_RECONNECT_ATTACH_ATTEMPTS = 10
_RECONNECT_ATTACH_RETRY_DELAY_SECONDS = 0.1
_CONSOLE_SSE_HEARTBEAT_SECONDS = 15
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
    return resolve_scope_preferred_tenant_id(
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
_BASE_AGENT_REQUEST_KEYS = frozenset(
    {
        "input",
        "session_id",
        "user_id",
        "channel",
        "reconnect",
    },
)
_PLAN_INTERACTION_RESPONSE_KEY = "plan_interaction_response"
_PLAN_MODE_META_KEY = "plan_mode_enabled"


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


def _extract_session_and_payload(request_data: Union[AgentRequest, dict]):
    """Extract run_key (ChatSpec.id), session_id, and native payload.

    Align with qwenpaw: keep full multimodal content parts (text/file/image/audio/video)
    instead of dropping non-text blocks.

    run_key must be ChatSpec.id (chat_id) so it matches list_chats/get_chat.
    """
    request_meta: dict[str, Any] = {}
    if isinstance(request_data, AgentRequest):
        channel_id = getattr(request_data, "channel", None) or "console"
        sender_id = request_data.user_id or "default"
        session_id = request_data.session_id or "default"
        content_parts = (
            list(request_data.input[0].content) if request_data.input else []
        )
        channel_meta = getattr(request_data, "channel_meta", None)
        if isinstance(channel_meta, dict):
            request_meta.update(channel_meta)

    else:
        channel_id = request_data.get("channel", "console")
        sender_id = request_data.get("user_id", "default")
        session_id = request_data.get("session_id", "default")
        input_data = request_data.get("input", [])
        request_meta.update(_extract_request_meta(request_data))

        content_parts = []
        for content_part in input_data:
            # pydantic model (rare in this branch) or plain dict
            if hasattr(content_part, "content"):
                content_parts.extend(list(content_part.content or []))
            elif isinstance(content_part, dict) and "content" in content_part:
                content_parts.extend(content_part.get("content") or [])

    native_payload: dict[str, Any] = {
        "channel_id": channel_id,
        "sender_id": sender_id,
        "content_parts": content_parts,
        "meta": {
            **request_meta,
            "session_id": session_id,
            "user_id": sender_id,
        },
    }
    return native_payload


def _extract_request_meta(request_data: dict[str, Any]) -> dict[str, Any]:
    """保留 Console 请求的计划元数据和未知扩展字段。"""
    meta = request_data.get("meta")
    request_meta = dict(meta) if isinstance(meta, dict) else {}
    for key, value in request_data.items():
        if key in _BASE_AGENT_REQUEST_KEYS or key == "meta":
            continue
        request_meta[key] = value
    return request_meta


def _is_exit_plan_response(meta: dict[str, Any]) -> bool:
    """判断本次请求是否是 Plan Review Card 的只退出动作。"""
    response = meta.get(_PLAN_INTERACTION_RESPONSE_KEY)
    return (
        isinstance(response, dict) and response.get("decision") == "exit_plan"
    )


def _plan_review_response(meta: dict[str, Any]) -> dict[str, Any] | None:
    """提取 Plan Review Card 的审核响应。"""
    response = meta.get(_PLAN_INTERACTION_RESPONSE_KEY)
    if not isinstance(response, dict):
        return None
    decision = response.get("decision")
    if decision not in {"revise", "execute", "exit_plan"}:
        return None
    return response


def _accepted_plan_context(plan: Any) -> dict[str, Any]:
    """构造传给执行轮次的只读计划上下文。"""
    return {
        "plan_id": plan.plan_id,
        "title": plan.title,
        "summary": plan.summary,
        "steps": list(plan.steps),
        "risks": list(plan.risks),
        "verification": list(plan.verification),
        "open_questions": list(plan.open_questions),
        "confidence": plan.confidence,
    }


async def _record_plan_review_decision(
    workspace: Any,
    chat: Any,
    meta: dict[str, Any],
) -> dict[str, Any] | None:
    """记录计划审核决策，execute 时只从后端持久化记录构造上下文。"""
    response = _plan_review_response(meta)
    if response is None:
        return None

    decision = response.get("decision")
    if decision not in {"revise", "execute", "exit_plan"}:
        raise HTTPException(status_code=400, detail="Invalid plan response")
    plan_id = response.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id:
        raise HTTPException(status_code=400, detail="plan_id is required")

    from ..plans import JsonProposedPlanStore, PlanService

    service = PlanService(JsonProposedPlanStore(Path(workspace.workspace_dir)))
    try:
        plan = await service.record_decision(
            chat_id=chat.id,
            plan_id=plan_id,
            decision=decision,
            feedback=response.get("feedback"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if decision == "execute":
        accepted = await service.load_accepted_plan(chat.id, plan.plan_id)
        if accepted is None:
            raise HTTPException(
                status_code=404,
                detail="accepted plan not found",
            )
        meta["accepted_plan"] = _accepted_plan_context(accepted)

    chat.meta = {
        **(getattr(chat, "meta", None) or {}),
        _PLAN_MODE_META_KEY: decision == "revise",
    }
    meta[_PLAN_MODE_META_KEY] = decision == "revise"
    chat_manager = getattr(workspace, "chat_manager", None)
    if chat_manager is not None and hasattr(chat_manager, "update_chat"):
        await chat_manager.update_chat(chat)

    return meta.get("accepted_plan")


def _build_exit_plan_stream(chat_id: str) -> StreamingResponse:
    """返回一个不启动 Main Agent 的 SSE 响应。"""

    async def event_generator() -> AsyncGenerator[str, None]:
        yield ": keep-alive\n\n"
        payload = {
            "object": "plan_interaction",
            "status": "completed",
            "type": "exit_plan",
            "chat_id": chat_id,
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _stream_with_keepalive(event_generator()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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


async def _resolve_raw_console_request_data(
    request_data: Union[AgentRequest, dict],
    request: Request,
) -> Union[AgentRequest, dict]:
    """在 FastAPI 丢弃扩展字段时回读原始 JSON 请求体。"""
    if not isinstance(request_data, AgentRequest):
        return request_data

    try:
        raw_body = await request.json()
        if isinstance(raw_body, dict):
            return raw_body
    except Exception:
        # 原始 JSON 仅用于保留扩展元数据，失败时仍按已解析模型处理。
        return request_data
    return request_data


def _inject_console_request_meta(
    native_payload: dict[str, Any],
    request: Request,
) -> None:
    """把中间件解析出的租户上下文写入 native payload 元数据。"""
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

    request_state = getattr(request, "state", None)
    if not request_state:
        return

    user_name = getattr(request_state, "user_name", None)
    bbk_id = getattr(request_state, "bbk_id", None)
    if user_name:
        native_payload["meta"]["user_name"] = user_name
    if bbk_id:
        native_payload["meta"]["bbk_id"] = bbk_id


async def _prepare_console_chat_queue(
    *,
    workspace: Any,
    tracker: Any,
    console_channel: Any,
    native_payload: dict[str, Any],
    session_id: str,
    is_reconnect: bool,
) -> tuple[Any, str, StreamingResponse | None]:
    """根据 reconnect 或新请求准备 SSE 队列，并处理纯退出计划模式。"""
    if is_reconnect:
        queue, run_key = await _attach_reconnect_queue(
            workspace,
            tracker,
            session_id,
            native_payload["channel_id"],
        )
        return queue, run_key, None

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
    if _plan_review_response(native_payload["meta"]):
        await _record_plan_review_decision(
            workspace,
            chat,
            native_payload["meta"],
        )
    if _is_exit_plan_response(native_payload["meta"]):
        return None, chat.id, _build_exit_plan_stream(chat.id)

    queue, _ = await tracker.attach_or_start(
        chat.id,
        native_payload,
        console_channel.stream_one,
    )
    return queue, chat.id, None


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
        raw_request_data = await _resolve_raw_console_request_data(
            request_data,
            request,
        )
        native_payload = _extract_session_and_payload(raw_request_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    _inject_console_request_meta(native_payload, request)

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

    queue, run_key, short_circuit = await _prepare_console_chat_queue(
        workspace=workspace,
        tracker=tracker,
        console_channel=console_channel,
        native_payload=native_payload,
        session_id=session_id,
        is_reconnect=(
            isinstance(request_data, dict)
            and request_data.get("reconnect") is True
        ),
    )
    if short_circuit is not None:
        return short_circuit
    if queue is None:
        raise HTTPException(
            status_code=404,
            detail="No running chat for this session",
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
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
