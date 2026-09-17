# -*- coding: utf-8 -*-
"""Explicit task progress update tool."""

import logging
from typing import Any, Literal

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from ...app.source_system_config import is_chat_task_progress_enabled
from ...app.source_system_config.runtime import (
    get_current_source_system_config,
)
from ...config.context import (
    get_current_task_progress_chat_id,
    get_current_task_progress_tracker,
    get_current_task_progress_turn_id,
)
from ...app.runner.task_progress import normalize_task_progress_payload

logger = logging.getLogger("swe.task_progress")


async def update_task_progress(
    items: list[dict[str, Any]],
    title: str | None = None,
    current_step_index: int | None = None,
    phase_status: Literal["active", "completed", "cancelled"] = "active",
) -> ToolResponse:
    """创建并维护当前轮次的步骤进度清单，让用户看到你在做什么。

    对于任何非简单的用户请求，在开始实质性工作之前，先用 3~6 个简短的中文步骤
    调用本工具一次以建立计划。每完成一个阶段后再调用一次，将该步骤标记为 done
    并将下一项推进为 running。始终保持恰好一个 running 步骤，全部完成时调用并
    传入 phase_status="completed"。

    参数说明：
    - title: 整轮任务的标题（可选，可为 null）
    - items: 步骤数组，每项含 label(中文标题)、status("todo"|"running"|"done")、
      id(可选，自动生成)。禁止传入 title/description 等未定义字段。
    - current_step_index: 当前执行步骤的序号(1-based)，可选
    - phase_status: "active"(进行中) | "completed"(已完成) | "cancelled"(已取消)

    仅在单步简单任务或纯对话提问时可跳过。
    """
    tracker = get_current_task_progress_tracker()
    chat_id = get_current_task_progress_chat_id()
    turn_id = get_current_task_progress_turn_id()

    logger.info(
        "update_task_progress CALLED: title=%r items_count=%d "
        "tracker_ok=%s chat_id=%s turn_id=%s",
        title,
        len(items),
        tracker is not None,
        chat_id,
        turn_id,
    )

    if not is_chat_task_progress_enabled(
        get_current_source_system_config(),
    ):
        logger.info(
            "update_task_progress SKIPPED: disabled for current source",
        )
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=(
                        '{"ok":true,"skipped":true,'
                        '"reason":"task progress disabled"}'
                    ),
                ),
            ],
        )

    if tracker is None or not chat_id or not turn_id:
        logger.warning(
            "update_task_progress CONTEXT MISSING: tracker=%s chat_id=%s turn_id=%s",
            "set" if tracker is not None else "None",
            chat_id,
            turn_id,
        )
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text='{"ok":false,"reason":"task progress context unavailable"}',
                ),
            ],
        )

    existing = await tracker.get_task_progress(chat_id)
    next_version = (existing.version + 1) if existing is not None else 1
    normalized_title = title.strip() if isinstance(title, str) else None
    payload = normalize_task_progress_payload(
        turn_id=turn_id,
        title=normalized_title or None,
        items=items,
        current_step_index=current_step_index,
        version=next_version,
        phase_status=phase_status,
    )
    await tracker.update_task_progress(chat_id, payload)
    logger.info(
        "update_task_progress OK: turn_id=%s version=%d steps=%d phase=%s",
        turn_id,
        next_version,
        len(payload.items),
        phase_status,
    )

    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text='{"ok":true}',
            ),
        ],
    )
