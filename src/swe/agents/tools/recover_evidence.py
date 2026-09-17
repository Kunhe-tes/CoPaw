# -*- coding: utf-8 -*-
"""Request-bound recovery of evidence referenced by a Chat checkpoint."""

import logging
from typing import Any, Sequence

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

logger = logging.getLogger(__name__)


def create_recover_evidence_tool(
    memory_manager: Any,
    *,
    chat_id: str,
    epoch: int,
):
    """Build a tool whose Chat and Context Epoch cannot be caller supplied."""

    async def recover_evidence(
        refs: Sequence[str] | None = None,
        query: str | None = None,
        kinds: Sequence[str] | None = None,
        time_range: str | None = None,
        limit: int = 3,
    ) -> ToolResponse:
        """Recover bounded, current-epoch evidence by durable references."""
        if memory_manager is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text="Memory manager is unavailable.",
                    ),
                ],
            )
        try:
            bounded_limit = min(max(int(limit), 1), 10)
        except (TypeError, ValueError):
            bounded_limit = 3
        try:
            messages = await memory_manager.recover_evidence(
                chat_id=chat_id,
                epoch=epoch,
                refs=list(refs or ()),
                query=query,
                kinds=list(kinds) if kinds is not None else None,
                time_range=time_range,
                limit=bounded_limit,
            )
        except Exception:  # Tool responses must not leak archive paths.
            logger.exception("Bounded evidence recovery failed")
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text="Evidence recovery is unavailable.",
                    ),
                ],
            )
        text = "\n\n".join(
            f"[{message.role}] {message.get_text_content()}"
            for message in messages[:bounded_limit]
        )
        return ToolResponse(
            content=[
                TextBlock(type="text", text=text or "No matching evidence."),
            ],
        )

    return recover_evidence
