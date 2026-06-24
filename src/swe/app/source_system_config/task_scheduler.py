# -*- coding: utf-8 -*-
"""Source 级系统任务调度器。

负责把 source 系统配置中的任务会话清理配置同步到外部调度平台，
并把外部 job id 与 source 级系统任务绑定关系持久化到绑定存储。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from swe.app.crons.manager import TASK_SESSION_CLEANUP_TASK_TYPE
from swe.app.crons.scheduler_adapter import SchedulerAdapter
from swe.config.context import encode_scope_id

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
        scheduler_from_id: str | None = None,
        updated_by: str | None = None,
    ) -> SourceSystemTaskBinding:
        """创建或更新 source 系统任务绑定。"""


class SourceTenantScopeStoreLike(Protocol):
    """按 source 查询 tenant 初始化记录的最小接口。"""

    async def get_by_source(
        self,
        source_id: str,
        *,
        include_templates: bool = False,
    ) -> list[dict[str, Any]]:
        """返回 source 下的 tenant 初始化记录。"""


class SourceWorkspaceManagerLike(Protocol):
    """按 runtime scope 获取工作区的最小接口。"""

    async def get_agent(
        self,
        agent_id: str,
        tenant_id: str | None = None,
    ) -> object:
        """返回指定 agent 和 runtime tenant scope 对应的工作区。"""


class SourceSystemTaskScheduler:
    """同步 source 级系统任务到外部调度平台。"""

    def __init__(
        self,
        binding_store: SourceSystemTaskBindingStore | SourceTaskBindingStoreLike,
        scheduler_adapter: SchedulerAdapter,
        callback_url: str,
        tenant_scope_store: SourceTenantScopeStoreLike | None = None,
        tenant_scope_store_factory: (
            Callable[[], SourceTenantScopeStoreLike | None] | None
        ) = None,
        multi_agent_manager: SourceWorkspaceManagerLike | None = None,
        agent_id: str = "default",
    ) -> None:
        """初始化调度器依赖。"""
        self._binding_store = binding_store
        self._scheduler_adapter = scheduler_adapter
        self._callback_url = callback_url
        self._tenant_scope_store = tenant_scope_store
        self._tenant_scope_store_factory = tenant_scope_store_factory
        self._multi_agent_manager = multi_agent_manager
        self._agent_id = agent_id

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

    async def run_task_session_cleanup(
        self,
        *,
        source_id: str,
    ) -> dict[str, Any]:
        """清理指定 source 下所有 runtime scope 的任务会话历史。"""
        result: dict[str, Any] = {
            "source_id": source_id,
            "scopes_seen": 0,
            "scopes_failed": 0,
            "sessions_seen": 0,
            "sessions_cleaned": 0,
            "sessions_skipped_locked": 0,
            "runs_removed": 0,
            "messages_removed": 0,
            "results": [],
            "errors": [],
        }
        tenant_scope_store = self._get_tenant_scope_store()
        if tenant_scope_store is None or self._multi_agent_manager is None:
            result["errors"].append("source cleanup dependencies unavailable")
            return result

        rows = await tenant_scope_store.get_by_source(
            source_id,
            include_templates=False,
        )
        result["scopes_seen"] = len(rows)
        for row in rows:
            await self._run_scope_cleanup(source_id, row, result)
        return result

    def _get_tenant_scope_store(self) -> SourceTenantScopeStoreLike | None:
        """运行时获取 tenant/source 初始化来源存储。"""
        if self._tenant_scope_store is not None:
            return self._tenant_scope_store
        if self._tenant_scope_store_factory is None:
            return None
        return self._tenant_scope_store_factory()

    async def _run_scope_cleanup(
        self,
        source_id: str,
        row: dict[str, Any],
        summary: dict[str, Any],
    ) -> None:
        """执行单个 runtime scope 的清理并把结果累加到 source 汇总。"""
        tenant_id = str(row.get("tenant_id") or "")
        row_source_id = str(row.get("source_id") or source_id)
        runtime_tenant_id = ""
        try:
            if not tenant_id:
                raise RuntimeError("tenant_id missing")
            runtime_tenant_id = encode_scope_id(tenant_id, row_source_id)
            assert self._multi_agent_manager is not None
            workspace = await self._multi_agent_manager.get_agent(
                self._agent_id,
                tenant_id=runtime_tenant_id,
            )
            cron_manager = getattr(workspace, "cron_manager", None)
            if cron_manager is None:
                raise RuntimeError("CronManager not found")
            scope_result = await cron_manager.run_task_session_cleanup()
            self._merge_scope_cleanup_result(
                summary,
                tenant_id,
                runtime_tenant_id,
                scope_result,
            )
        except Exception as exc:  # noqa: BLE001
            summary["scopes_failed"] += 1
            summary["errors"].append(
                {
                    "tenant_id": tenant_id,
                    "runtime_tenant_id": runtime_tenant_id,
                    "error": str(exc),
                },
            )

    @staticmethod
    def _merge_scope_cleanup_result(
        summary: dict[str, Any],
        tenant_id: str,
        runtime_tenant_id: str,
        scope_result: dict[str, Any] | None,
    ) -> None:
        """把单个 scope 的清理结果累加到 source 汇总。"""
        result = scope_result if isinstance(scope_result, dict) else {}
        summary["results"].append(
            {
                "tenant_id": tenant_id,
                "runtime_tenant_id": runtime_tenant_id,
                **result,
            },
        )
        for key in (
            "sessions_seen",
            "sessions_cleaned",
            "sessions_skipped_locked",
            "runs_removed",
            "messages_removed",
        ):
            summary[key] += int(result.get(key, 0) or 0)
