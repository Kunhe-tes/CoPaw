# -*- coding: utf-8 -*-
"""Request-bound recovery of evidence referenced by a Chat checkpoint."""

from typing import Any, Sequence

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse


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
        bounded_limit = min(max(int(limit), 1), 10)
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
        except Exception as exc:  # Tool responses must not leak archive paths.
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Evidence recovery failed: {exc}",
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
