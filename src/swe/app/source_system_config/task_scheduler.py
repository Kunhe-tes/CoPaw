# -*- coding: utf-8 -*-
"""Source 级系统任务调度器。

负责把 source 系统配置中的任务会话清理配置同步到外部调度平台，
并把外部 job id 与 source 级系统任务绑定关系持久化到绑定存储。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from swe.app.crons.manager import TASK_SESSION_CLEANUP_TASK_TYPE
from swe.app.crons.scheduler_adapter import SchedulerAdapter

from .task_binding_store import (
    SourceSystemTaskBinding,
    SourceSystemTaskBindingStore,
)

from .runtime import resolve_cron_task_session_cleanup_config

SOURCE_TASK_SESSION_CLEANUP_JOB_ID = "_source_task_session_cleanup"
SOURCE_TASK_SESSION_CLEANUP_NAME = "task_session_cleanup"


@dataclass(frozen=True, slots=True)
class SourceSchedulerIdentity:
    """记录最后一次修改 source 系统任务配置的调度身份。"""

    tenant_id: str
    scope_id: str
    from_id: str
    updated_by: str | None = None


@dataclass(frozen=True, slots=True)
class SourceTaskSessionCleanupRefreshResult:
    """描述 source 级 cleanup 调度刷新的结果。"""

    action: str
    binding: SourceSystemTaskBinding | None = None


class SourceTaskBindingStoreLike(Protocol):
    """source 系统任务绑定存储所需的最小接口。"""

    async def get_binding(
        self,
        source_id: str,
        task_type: str,
    ) -> SourceSystemTaskBinding | None:
        """读取 source 系统任务绑定。"""

    async def upsert_binding(
        self,
        *,
        source_id: str,
        task_type: str,
        external_job_id: str,
        cron: str,
        enabled: bool,
        scheduler_tenant_id: str | None = None,
        scheduler_scope_id: str | None = None,
        scheduler_from_id: str | None = None,
        updated_by: str | None = None,
    ) -> SourceSystemTaskBinding:
        """创建或更新 source 系统任务绑定。"""


class SourceSystemTaskScheduler:
    """同步 source 级系统任务到外部调度平台。"""

    def __init__(
        self,
        binding_store: SourceSystemTaskBindingStore | SourceTaskBindingStoreLike,
        scheduler_adapter: SchedulerAdapter,
        callback_url: str,
    ) -> None:
        """初始化调度器依赖。"""
        self._binding_store = binding_store
        self._scheduler_adapter = scheduler_adapter
        self._callback_url = callback_url

    async def refresh_task_session_cleanup(
        self,
        source_id: str,
        config: object,
        identity: SourceSchedulerIdentity,
    ) -> SourceTaskSessionCleanupRefreshResult:
        """按 source 配置注册、更新或暂停任务会话清理外部任务。"""
        cleanup_config = resolve_cron_task_session_cleanup_config(config)
        binding = await self._binding_store.get_binding(
            source_id,
            SOURCE_TASK_SESSION_CLEANUP_NAME,
        )
        external_job_id = binding.external_job_id if binding else ""

        if not cleanup_config.enabled:
            if not external_job_id:
                return SourceTaskSessionCleanupRefreshResult(
                    action="disabled",
                )
            await self._scheduler_adapter.pause_job(external_job_id)
            persisted_binding = await self._binding_store.upsert_binding(
                source_id=source_id,
                task_type=SOURCE_TASK_SESSION_CLEANUP_NAME,
                external_job_id=external_job_id,
                cron=cleanup_config.cron,
                enabled=False,
                scheduler_tenant_id=identity.tenant_id,
                scheduler_scope_id=identity.scope_id,
                scheduler_from_id=identity.from_id,
                updated_by=identity.updated_by,
            )
            return SourceTaskSessionCleanupRefreshResult(
                action="paused",
                binding=persisted_binding,
            )

        scheduler_kwargs = {
            "tenant_id": identity.tenant_id,
            "source_id": source_id,
            "agent_id": "",
            "task_type": TASK_SESSION_CLEANUP_TASK_TYPE,
            "job_id": SOURCE_TASK_SESSION_CLEANUP_JOB_ID,
            "job_name": SOURCE_TASK_SESSION_CLEANUP_NAME,
            "cron": cleanup_config.cron,
            "callback_url": self._callback_url,
            "source_level": True,
            "scope_id": identity.scope_id,
            "from_id": identity.from_id,
        }

        action = "registered"
        if external_job_id:
            await self._scheduler_adapter.update_job(
                external_id=external_job_id,
                **scheduler_kwargs,
            )
            await self._scheduler_adapter.resume_job(external_job_id)
            action = "updated"
        else:
            external_job_id = await self._scheduler_adapter.register_job(
                **scheduler_kwargs,
            )
            self._require_external_job_id(source_id, external_job_id)

        persisted_binding = await self._binding_store.upsert_binding(
            source_id=source_id,
            task_type=SOURCE_TASK_SESSION_CLEANUP_NAME,
            external_job_id=external_job_id,
            cron=cleanup_config.cron,
            enabled=True,
            scheduler_tenant_id=identity.tenant_id,
            scheduler_scope_id=identity.scope_id,
            scheduler_from_id=identity.from_id,
            updated_by=identity.updated_by,
        )
        return SourceTaskSessionCleanupRefreshResult(
            action=action,
            binding=persisted_binding,
        )

    def _require_external_job_id(
        self,
        source_id: str,
        external_job_id: str,
    ) -> None:
        """校验外部调度返回了可持久化的 job id。"""
        if external_job_id:
            return
        raise RuntimeError(
            "external scheduler did not return job id "
            f"for source cleanup task: {source_id}",
        )
