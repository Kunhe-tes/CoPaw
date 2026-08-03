# -*- coding: utf-8 -*-
"""Bound tool-result output before it reaches AgentScope print and memory."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from agentscope.message import Msg

from swe.app.source_system_config.runtime import (
    resolve_tool_result_compact_config,
)

from .utils.tool_output_compaction import compact_tool_result_messages


class ToolOutputBudgetMixin:
    """Apply the recoverable tool-output budget at AgentScope's boundary."""

    async def _acting(self, tool_call) -> dict | None:
        """Execute a tool call with its displayed and stored output bounded."""
        tool_res_msg = Msg(
            "system",
            [
                {
                    "type": "tool_result",
                    "id": tool_call["id"],
                    "name": tool_call["name"],
                    "output": [],
                },
            ],
            "system",
        )
        try:
            tool_res = await self.toolkit.call_tool_function(tool_call)
            tool_result_compact = resolve_tool_result_compact_config(
                self._agent_config.running.tool_result_compact,
            )
            workspace_dir = self._workspace_dir

            async for chunk in tool_res:
                output: Any = chunk.content
                if tool_result_compact.enabled and workspace_dir is not None:
                    compacted_chunk_msg = Msg(
                        "system",
                        [
                            {
                                "type": "tool_result",
                                "id": tool_call["id"],
                                "name": tool_call["name"],
                                "output": output,
                            },
                        ],
                        "system",
                    )
                    compact_tool_result_messages(
                        [compacted_chunk_msg],
                        old_max_bytes=tool_result_compact.recent_max_bytes,
                        recent_max_bytes=tool_result_compact.recent_max_bytes,
                        recent_n=1,
                        artifact_dir=Path(workspace_dir) / "tool_result",
                        workspace_dir=Path(workspace_dir),
                    )
                    output = compacted_chunk_msg.content[0]["output"]

                tool_res_msg.content[0]["output"] = output
                await self.print(tool_res_msg, chunk.is_last)

                if chunk.is_interrupted:
                    raise asyncio.CancelledError()

                if (
                    tool_call["name"] == self.finish_function_name
                    and chunk.metadata
                    and chunk.metadata.get("success", False)
                ):
                    return chunk.metadata.get("structured_output")

            return None
        finally:
            await self.memory.add(tool_res_msg)
