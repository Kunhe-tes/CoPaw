# -*- coding: utf-8 -*-
"""Chat context operations available to expert main executions."""


class ExpertMainMemoryManager:
    """Allow Chat compaction/checkpoints without Profile memory access."""

    def __init__(self, manager):
        self._manager = manager
        self.agent_id = manager.agent_id
        self.tenant_id = getattr(manager, "tenant_id", None)

    def create_request_memory(self, chat_id):
        """Create an isolated Chat memory and exclude Profile recall."""
        memory = self._manager.create_request_memory(chat_id)
        if memory is not None and hasattr(memory, "_long_term_memory"):
            memory._long_term_memory = ""
        return memory

    async def compact_tool_result(self, **kwargs):
        return await self._manager.compact_tool_result(**kwargs)

    async def check_context(self, **kwargs):
        return await self._manager.check_context(**kwargs)

    async def compact_memory(self, **kwargs):
        return await self._manager.compact_memory(**kwargs)

    async def schedule_precompaction(self, **kwargs):
        return await self._manager.schedule_precompaction(**kwargs)

    async def install_ready_precompaction(self, **kwargs):
        return await self._manager.install_ready_precompaction(**kwargs)

    async def install_degraded_checkpoint(self, **kwargs):
        return await self._manager.install_degraded_checkpoint(**kwargs)

    async def reset_context_epoch(self, **kwargs):
        return await self._manager.reset_context_epoch(**kwargs)

    def add_async_summary_task(self, **_kwargs):
        """Expert conversation context must never become Profile memory."""
        return None
