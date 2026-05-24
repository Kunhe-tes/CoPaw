# -*- coding: utf-8 -*-
"""Main-agent tool for compact SubAgent delegation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

from ...app.subagents import (
    DelegationManager,
    DelegationSpec,
    PermissionPolicy,
)


def create_delegate_to_subagent_tool(
    *,
    manager: DelegationManager | None,
    parent_agent_config: Any,
    workspace_dir: Path | None,
    request_context: dict[str, Any],
):
    """Create a closure-bound delegation tool for a main SWEAgent."""

    async def delegate_to_subagent(
        agent_name: str,
        objective: str,
        background: str = "",
    ) -> ToolResponse:
        """Delegate readonly research to a named SubAgent.

        Args:
            agent_name: Name of the SubAgent definition to run.
            objective: Focused objective for the SubAgent.
            background: Optional parent-context summary.

        Returns:
            Compact AgentResult JSON.
        """
        active_manager = manager or DelegationManager()
        spec = DelegationSpec(
            parent_thread_id=str(request_context.get("session_id") or ""),
            agent_name=agent_name,
            objective=objective,
            background=background,
        )
        result = await active_manager.delegate(
            spec=spec,
            parent_agent_config=parent_agent_config,
            workspace_dir=Path(workspace_dir or "."),
            parent_policy=PermissionPolicy.readonly(),
            request_context=request_context,
        )
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=json.dumps(
                        result.model_dump(mode="json"),
                        ensure_ascii=False,
                    ),
                ),
            ],
        )

    return delegate_to_subagent
