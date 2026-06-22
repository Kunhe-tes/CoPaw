# -*- coding: utf-8 -*-
"""技能可执行性异步运行器。"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from ..tenant_context import bind_tenant_context
from .models import (
    SkillReadinessCheckConfig,
    SkillReadinessCheckResult,
    SkillReadinessConfig,
    SkillReadinessOwner,
    SkillReadinessUserResult,
)
from .store import SkillReadinessStore
from .strategies import (
    SkillReadinessCheckContext,
    SkillReadinessStrategyRegistry,
)

logger = logging.getLogger(__name__)

DEFAULT_USER_CONCURRENCY = 10
DEFAULT_USER_TIMEOUT_SECONDS = 60.0


class SkillReadinessRunner:
    """调度并持久化一次技能可执行性检查。"""

    def __init__(
        self,
        store: SkillReadinessStore,
        registry: SkillReadinessStrategyRegistry,
        *,
        multi_agent_manager: Any | None = None,
        agent_id: str = "default",
        user_concurrency: int = DEFAULT_USER_CONCURRENCY,
        user_timeout_seconds: float = DEFAULT_USER_TIMEOUT_SECONDS,
    ):
        self.store = store
        self.registry = registry
        self.multi_agent_manager = multi_agent_manager
        self.agent_id = agent_id
        self.user_concurrency = max(1, user_concurrency)
        self.user_timeout_seconds = max(1.0, user_timeout_seconds)

    def schedule(
        self,
        *,
        run_id: str,
        source_id: str,
        skill_id: str,
        owners: list[SkillReadinessOwner],
        config: SkillReadinessConfig,
        partial_failure_summary: str | None = None,
    ) -> asyncio.Task:
        """创建后台任务，调用方不需要等待结果。"""
        return asyncio.create_task(
            self.run(
                run_id=run_id,
                source_id=source_id,
                skill_id=skill_id,
                owners=owners,
                config=config,
                partial_failure_summary=partial_failure_summary,
            ),
            name=f"skill-readiness-{run_id}",
        )

    async def run(
        self,
        *,
        run_id: str,
        source_id: str,
        skill_id: str,
        owners: list[SkillReadinessOwner],
        config: SkillReadinessConfig,
        partial_failure_summary: str | None = None,
    ) -> None:
        """执行完整 owner 集合的检查并更新运行状态。"""
        try:
            await self.store.update_run_progress(
                run_id,
                total_users=len(owners),
            )
            if not owners:
                await self.store.update_run_progress(
                    run_id,
                    status="completed",
                    completed_at=_utc_now(),
                )
                return

            semaphore = asyncio.Semaphore(self.user_concurrency)
            results = await asyncio.gather(
                *[
                    self._run_one_user_guarded(
                        semaphore,
                        run_id,
                        source_id,
                        skill_id,
                        owner,
                        config,
                    )
                    for owner in owners
                ],
                return_exceptions=True,
            )
            task_failures = [
                str(result)
                for result in results
                if isinstance(result, Exception)
            ]
            failure_summary = _join_failure_summaries(
                partial_failure_summary,
                "; ".join(task_failures) if task_failures else None,
            )
            await self.store.update_run_progress(
                run_id,
                status=(
                    "failed"
                    if task_failures
                    else "partial"
                    if partial_failure_summary
                    else "completed"
                ),
                failure_summary=failure_summary,
                completed_at=_utc_now(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("skill readiness run failed: %s", run_id)
            await self.store.update_run_progress(
                run_id,
                status="failed",
                failure_summary=str(exc),
                completed_at=_utc_now(),
            )

    async def _run_one_user_guarded(
        self,
        semaphore: asyncio.Semaphore,
        run_id: str,
        source_id: str,
        skill_id: str,
        owner: SkillReadinessOwner,
        config: SkillReadinessConfig,
    ) -> None:
        async with semaphore:
            with bind_tenant_context(
                tenant_id=owner.user_id,
                user_id=owner.user_id,
                source_id=source_id,
            ):
                user_result = await self._run_one_user(
                    source_id,
                    skill_id,
                    owner,
                    config,
                )
            await self.store.record_user_result(run_id, user_result)

    async def _run_one_user(
        self,
        source_id: str,
        skill_id: str,
        owner: SkillReadinessOwner,
        config: SkillReadinessConfig,
    ) -> SkillReadinessUserResult:
        started_at = time.perf_counter()
        checks: list[SkillReadinessCheckResult] = []
        enabled_checks = config.enabled_checks()
        context = await self._build_context(source_id, skill_id, owner)
        deadline = asyncio.get_running_loop().time() + self.user_timeout_seconds

        for index, check_config in enumerate(enabled_checks):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                checks.extend(
                    self._timeout_results(enabled_checks[index:]),
                )
                break
            try:
                result = await asyncio.wait_for(
                    self.registry.run_check(context, check_config),
                    timeout=remaining,
                )
                checks.append(result)
            except asyncio.TimeoutError:
                checks.extend(
                    self._timeout_results(enabled_checks[index:]),
                )
                break

        failed_count = sum(1 for check in checks if check.status == "fail")
        return SkillReadinessUserResult(
            user_id=owner.user_id,
            user_name=owner.user_name,
            bbk_id=owner.bbk_id,
            aggregate_status="abnormal" if failed_count else "normal",
            summary=(
                f"{failed_count} checks failed"
                if failed_count
                else "all checks passed or skipped"
            ),
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            checks=checks,
        )

    async def _build_context(
        self,
        source_id: str,
        skill_id: str,
        owner: SkillReadinessOwner,
    ) -> SkillReadinessCheckContext:
        workspace = None
        if self.multi_agent_manager is not None:
            try:
                workspace = await self.multi_agent_manager.get_agent(
                    self.agent_id,
                    tenant_id=(
                        SkillReadinessCheckContext(
                            source_id=source_id,
                            skill_id=skill_id,
                            owner=owner,
                        ).scope_id
                    ),
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "failed to load workspace for readiness user=%s",
                    owner.user_id,
                    exc_info=True,
                )
        return SkillReadinessCheckContext(
            source_id=source_id,
            skill_id=skill_id,
            owner=owner,
            cron_manager=getattr(workspace, "cron_manager", None),
            workspace=workspace,
        )

    def _timeout_results(
        self,
        check_configs: list[SkillReadinessCheckConfig],
    ) -> list[SkillReadinessCheckResult]:
        return [
            SkillReadinessCheckResult(
                check_name=check_config.name,
                display_name=self.registry.display_name_for(
                    check_config.name,
                ),
                status="fail",
                message="用户自检超时",
                details={"timeout_seconds": self.user_timeout_seconds},
                duration_ms=0,
            )
            for check_config in check_configs
        ]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _join_failure_summaries(*summaries: str | None) -> str | None:
    parts = [summary for summary in summaries if summary]
    return "; ".join(parts) if parts else None
