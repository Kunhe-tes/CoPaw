# -*- coding: utf-8 -*-
"""技能可执行性应用服务。"""

from __future__ import annotations

import logging
from typing import Any

from .models import (
    SkillReadinessConfig,
    SkillReadinessConfigCheckSummary,
    SkillReadinessOverview,
    SkillReadinessOwnerSummary,
    SkillReadinessResultsPage,
    SkillReadinessRunProgress,
    SkillReadinessRunSummary,
    SkillReadinessStartRunResponse,
)
from .owner_resolver import OwnerLookupResult, SkillOwnerResolver
from .runner import SkillReadinessRunner
from .store import SkillReadinessStore
from .strategies import SkillReadinessStrategyRegistry

logger = logging.getLogger(__name__)


class SkillReadinessConfigMissing(ValueError):
    """技能没有配置自检项。"""


class SkillReadinessConfigNotStartable(ValueError):
    """技能自检配置存在但没有启用项。"""


class SkillReadinessRunNotFound(ValueError):
    """运行记录不存在。"""


class SkillReadinessService:
    """组合存储、owner 查询和运行器的业务服务。"""

    def __init__(
        self,
        store: SkillReadinessStore,
        owner_resolver: SkillOwnerResolver,
        registry: SkillReadinessStrategyRegistry,
        runner: SkillReadinessRunner,
    ):
        self.store = store
        self.owner_resolver = owner_resolver
        self.registry = registry
        self.runner = runner

    async def get_overview(
        self,
        source_id: str,
        skill_id: str,
    ) -> SkillReadinessOverview:
        config_record = await self.store.get_config(skill_id)
        owner_lookup = await self._resolve_owners(source_id, skill_id)
        latest_run = await self.store.get_latest_run(source_id, skill_id)
        latest_summary = await self._build_run_summary(latest_run)

        config = config_record.config if config_record else None
        return SkillReadinessOverview(
            skill_id=skill_id,
            config_found=config is not None,
            startable=bool(config and config.is_startable),
            config_message=_config_message(config),
            config_checks=self._config_check_summaries(config),
            owner_summary=SkillReadinessOwnerSummary(
                total_users=len(owner_lookup.owners),
                lookup_failed_users=owner_lookup.failed_users,
                failure_summary=owner_lookup.failure_summary,
            ),
            owners=owner_lookup.owners,
            latest_run=latest_summary,
        )

    async def start_run(
        self,
        source_id: str,
        skill_id: str,
    ) -> SkillReadinessStartRunResponse:
        config_record = await self.store.get_config(skill_id)
        if config_record is None:
            raise SkillReadinessConfigMissing(
                "skill readiness config not found",
            )
        config = config_record.config
        if not config.is_startable:
            raise SkillReadinessConfigNotStartable(
                "skill readiness config has no enabled checks",
            )

        owner_lookup = await self._resolve_owners(source_id, skill_id)
        run, reused = await self.store.get_or_create_running_run(
            source_id,
            skill_id,
            config,
            owner_lookup_summary=owner_lookup.as_summary(),
        )
        if reused:
            return SkillReadinessStartRunResponse(run=run, reused=True)
        if not owner_lookup.owners and owner_lookup.failed_users:
            failed_run = await self.store.update_run_progress(
                run.run_id,
                total_users=owner_lookup.total_users,
                status="failed",
                failure_summary=owner_lookup.failure_summary,
            )
            return SkillReadinessStartRunResponse(run=failed_run, reused=False)

        run = await self.store.update_run_progress(
            run.run_id,
            total_users=len(owner_lookup.owners),
        )
        self.runner.schedule(
            run_id=run.run_id,
            source_id=source_id,
            skill_id=skill_id,
            owners=owner_lookup.owners,
            config=config,
            partial_failure_summary=owner_lookup.failure_summary,
        )
        return SkillReadinessStartRunResponse(run=run, reused=False)

    async def get_results(
        self,
        run_id: str,
        *,
        source_id: str,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
        check_name: str | None = None,
        check_status: str | None = None,
    ) -> SkillReadinessResultsPage:
        run = await self.store.get_run(run_id)
        if run is None:
            raise SkillReadinessRunNotFound(run_id)
        if run.source_id != source_id:
            raise SkillReadinessRunNotFound(run_id)
        items, total = await self.store.list_user_results(
            run_id,
            page=page,
            page_size=page_size,
            status=status,
            check_name=check_name,
            check_status=check_status,
        )
        return SkillReadinessResultsPage(
            run=run,
            items=items,
            total=total,
            page=max(page, 1),
            page_size=min(max(page_size, 1), 100),
        )

    async def _resolve_owners(
        self,
        source_id: str,
        skill_id: str,
    ) -> OwnerLookupResult:
        try:
            return await self.owner_resolver.resolve_owners(source_id, skill_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "skill readiness owner lookup failed: %s/%s",
                source_id,
                skill_id,
                exc_info=True,
            )
            return OwnerLookupResult(
                owners=[],
                total_users=0,
                failed_users=1,
                failures=[str(exc)],
            )

    def _config_check_summaries(
        self,
        config: SkillReadinessConfig | None,
    ) -> list[SkillReadinessConfigCheckSummary]:
        if config is None:
            return []
        return [
            SkillReadinessConfigCheckSummary(
                name=check.name,
                display_name=self.registry.display_name_for(check.name),
                enabled=check.enabled,
                params=check.params,
            )
            for check in config.checks
        ]

    async def _build_run_summary(
        self,
        run: SkillReadinessRunProgress | None,
    ) -> SkillReadinessRunSummary | None:
        if run is None:
            return None
        return SkillReadinessRunSummary(
            **run.model_dump(),
            check_summaries=await self.store.get_check_summaries(run.run_id),
        )


def _config_message(config: SkillReadinessConfig | None) -> str:
    if config is None:
        return "未查询到自检配置"
    if not config.is_startable:
        return "自检配置没有启用的检查项"
    return "已查询到自检配置"


def build_skill_readiness_service(
    store: SkillReadinessStore,
    *,
    multi_agent_manager: Any | None = None,
) -> SkillReadinessService:
    """构造默认技能可执行性服务。"""
    from .strategies import build_default_strategy_registry

    registry = build_default_strategy_registry()
    runner = SkillReadinessRunner(
        store,
        registry,
        multi_agent_manager=multi_agent_manager,
    )
    return SkillReadinessService(
        store=store,
        owner_resolver=SkillOwnerResolver(),
        registry=registry,
        runner=runner,
    )
