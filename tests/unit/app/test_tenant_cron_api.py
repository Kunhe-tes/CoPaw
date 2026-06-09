# -*- coding: utf-8 -*-
"""Tenant injection regression tests for cron APIs."""

import importlib.util
import sys
import types
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from swe.config.context import encode_scope_id

SRC_ROOT = Path(__file__).parent.parent.parent.parent / "src"
sys.path.insert(0, str(SRC_ROOT))

_ORIGINAL_MODULES = {
    name: sys.modules.get(name)
    for name in [
        "swe.app.crons",
        "swe.app.channels.schema",
        "swe.app.crons.models",
        "swe.app.crons.manager",
        "swe.app.crons.api",
    ]
}

if "swe.app.crons" not in sys.modules:
    pkg = types.ModuleType("swe.app.crons")
    pkg.__path__ = [str(SRC_ROOT / "swe" / "app" / "crons")]
    sys.modules["swe.app.crons"] = pkg

channels_schema_module = types.ModuleType("swe.app.channels.schema")
channels_schema_module.ChannelType = str
channels_schema_module.DEFAULT_CHANNEL = "console"
sys.modules["swe.app.channels.schema"] = channels_schema_module

models_spec = importlib.util.spec_from_file_location(
    "swe.app.crons.models",
    SRC_ROOT / "swe" / "app" / "crons" / "models.py",
)
assert models_spec is not None and models_spec.loader is not None
models_module = importlib.util.module_from_spec(models_spec)
sys.modules["swe.app.crons.models"] = models_module
models_spec.loader.exec_module(models_module)

manager_module = types.ModuleType("swe.app.crons.manager")
manager_module.CronManager = object
sys.modules["swe.app.crons.manager"] = manager_module

api_spec = importlib.util.spec_from_file_location(
    "swe.app.crons.api",
    SRC_ROOT / "swe" / "app" / "crons" / "api.py",
)
assert api_spec is not None and api_spec.loader is not None
api_module = importlib.util.module_from_spec(api_spec)
sys.modules["swe.app.crons.api"] = api_module
api_spec.loader.exec_module(api_module)

for _name, _module in _ORIGINAL_MODULES.items():
    if _module is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _module


class _TenantStateMiddleware:
    def __init__(
        self,
        app,
        tenant_id: str,
        source_id: str,
        user_name: str,
        bbk_id: str,
    ):
        self.app = app
        self.tenant_id = tenant_id
        self.source_id = source_id
        self.user_name = user_name
        self.bbk_id = bbk_id

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {})
            scope["state"]["tenant_id"] = self.tenant_id
            scope["state"]["source_id"] = self.source_id
            scope["state"]["scope_id"] = encode_scope_id(
                self.tenant_id,
                self.source_id,
            )
            scope["state"]["user_name"] = self.user_name
            scope["state"]["bbk_id"] = self.bbk_id
        await self.app(scope, receive, send)


class _Manager:
    def __init__(self, jobs_by_id: dict[str, object] | None = None):
        self.created = []
        self.jobs_by_id = dict(jobs_by_id or {})

    async def create_or_replace_job(self, spec):
        self.created.append(spec)
        self.jobs_by_id[spec.id] = spec

    async def list_jobs(self):
        return list(self.jobs_by_id.values())

    async def get_job(self, job_id):
        return self.jobs_by_id.get(job_id)

    def get_state(self, job_id):
        return types.SimpleNamespace(model_dump=lambda mode=None: {})


class _Provider:
    def __init__(self, models: list[str]):
        self._models = set(models)

    def has_model(self, model_id: str) -> bool:
        return model_id in self._models


class _ProviderManager:
    def __init__(self, providers: dict[str, _Provider]):
        self._providers = providers

    def get_provider(self, provider_id: str):
        return self._providers.get(provider_id)


class _Workspace:
    def __init__(self, cron_manager: _Manager):
        self.cron_manager = cron_manager


class _MultiAgentManager:
    def __init__(self, workspaces: dict[str, _Workspace]):
        self._workspaces = workspaces

    async def get_agent(self, _agent_id: str, tenant_id: str):
        return self._workspaces[tenant_id]


class _TenantWorkspacePool:
    async def ensure_bootstrap(
        self,
        _tenant_id: str,
        source_id: str | None = None,
    ):
        del source_id
        return None


CronJobSpec = models_module.CronJobSpec
ScheduleSpec = models_module.ScheduleSpec
DispatchSpec = models_module.DispatchSpec
DispatchTarget = models_module.DispatchTarget
JobRuntimeSpec = models_module.JobRuntimeSpec
CronJobRequest = models_module.CronJobRequest


def _job_spec(
    job_id: str = "",
    *,
    task_type: str = "agent",
    model_slot: dict | None = None,
):
    payload = {
        "id": job_id,
        "name": "tenant cron",
        "enabled": True,
        "tenant_id": None,
        "schedule": ScheduleSpec(cron="* * * * *").model_dump(mode="json"),
        "dispatch": DispatchSpec(
            channel="console",
            target=DispatchTarget(user_id="user-a", session_id="session-a"),
            meta={},
        ).model_dump(mode="json"),
        "runtime": JobRuntimeSpec().model_dump(mode="json"),
        "meta": {},
    }
    if task_type == "agent":
        payload.update(
            {
                "task_type": "agent",
                "request": CronJobRequest(
                    input=[{"content": [{"type": "text", "text": "ping"}]}],
                ).model_dump(mode="json"),
            },
        )
    else:
        payload.update(
            {
                "task_type": "text",
                "text": "hello cron",
            },
        )
    if model_slot is not None:
        payload["model_slot"] = model_slot
    return payload


def _install_provider_manager(
    providers: dict[str, _Provider],
    providers_by_tenant: dict[str, dict[str, _Provider]] | None = None,
):
    tenant_providers = dict(providers_by_tenant or {})
    api_module.ProviderManager = types.SimpleNamespace(  # type: ignore[attr-defined]
        ensure_tenant_provider_storage=lambda _tenant_id: None,
        get_instance=lambda tenant_id: _ProviderManager(
            tenant_providers.get(tenant_id, providers),
        ),
    )


def _model_slot(
    provider_id: str = "openai",
    model: str = "gpt-5.4",
) -> dict[str, str]:
    return {
        "provider_id": provider_id,
        "model": model,
    }


def _build_client(
    manager: _Manager,
    *,
    multi_agent_manager: _MultiAgentManager | None = None,
    tenant_workspace_pool: _TenantWorkspacePool | None = None,
) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        _TenantStateMiddleware,
        tenant_id="tenant-a",
        source_id="source-a",
        user_name="Alice",
        bbk_id="1001",
    )
    app.include_router(api_module.router)
    if multi_agent_manager is not None:
        app.state.multi_agent_manager = multi_agent_manager
    if tenant_workspace_pool is not None:
        app.state.tenant_workspace_pool = tenant_workspace_pool

    async def _get_mgr():
        return manager

    app.dependency_overrides[api_module.get_cron_manager] = _get_mgr
    return TestClient(app)


def test_create_job_injects_request_tenant_id():
    manager = _Manager()
    client = _build_client(manager)

    response = client.post("/cron/jobs", json=_job_spec())

    assert response.status_code == 200
    assert manager.created[0].tenant_id == "tenant-a"
    assert manager.created[0].source_id == "source-a"
    assert manager.created[0].scope_id == encode_scope_id(
        "tenant-a",
        "source-a",
    )
    assert manager.created[0].tenant_name == "Alice"
    assert manager.created[0].bbk_id == "1001"
    assert manager.created[0].model_slot is None
    assert response.json().get("model_slot") is None


def test_replace_job_overrides_payload_tenant_with_request_tenant():
    manager = _Manager()
    client = _build_client(manager)

    response = client.put(
        "/cron/jobs/job-1",
        json={**_job_spec("job-1"), "tenant_id": "other-tenant"},
    )

    assert response.status_code == 200
    assert manager.created[0].tenant_id == "tenant-a"
    assert manager.created[0].source_id == "source-a"
    assert manager.created[0].scope_id == encode_scope_id(
        "tenant-a",
        "source-a",
    )


def test_create_job_persists_model_slot():
    manager = _Manager()
    client = _build_client(manager)
    _install_provider_manager(
        {
            "openai": _Provider(["gpt-5.4"]),
        },
    )

    response = client.post(
        "/cron/jobs",
        json=_job_spec(model_slot=_model_slot()),
    )

    assert response.status_code == 200
    assert manager.created[0].model_slot is not None
    assert manager.created[0].model_slot.provider_id == "openai"
    assert manager.created[0].model_slot.model == "gpt-5.4"
    assert response.json()["model_slot"] == _model_slot()


def test_create_job_rejects_unknown_model_slot_provider():
    manager = _Manager()
    client = _build_client(manager)
    _install_provider_manager(
        {
            "openai": _Provider(["gpt-5.4"]),
        },
    )

    response = client.post(
        "/cron/jobs",
        json=_job_spec(
            model_slot=_model_slot(provider_id="missing-provider"),
        ),
    )

    assert response.status_code == 404
    assert (
        response.json()["detail"] == "Provider 'missing-provider' not found."
    )
    assert manager.created == []


def test_replace_job_rejects_unknown_model_slot_model():
    manager = _Manager()
    client = _build_client(manager)
    _install_provider_manager(
        {
            "openai": _Provider(["gpt-5.4"]),
        },
    )

    response = client.put(
        "/cron/jobs/job-1",
        json=_job_spec(
            "job-1",
            model_slot=_model_slot(model="gpt-4.1"),
        ),
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Model 'gpt-4.1' not found in provider 'openai'."
    )
    assert manager.created == []


def test_create_text_job_clears_model_slot():
    manager = _Manager()
    client = _build_client(manager)
    _install_provider_manager(
        {
            "openai": _Provider(["gpt-5.4"]),
        },
    )

    response = client.post(
        "/cron/jobs",
        json=_job_spec(
            task_type="text",
            model_slot=_model_slot(),
        ),
    )

    assert response.status_code == 200
    assert manager.created[0].task_type == "text"
    assert manager.created[0].model_slot is None
    assert response.json().get("model_slot") is None


def test_broadcast_clears_model_slot_and_returns_warning_for_unsupported_tenant():
    source_job = CronJobSpec.model_validate(
        {
            **_job_spec(
                "job-source",
                model_slot=_model_slot(),
            ),
            "schedule": ScheduleSpec(
                cron="0 9 * * *",
            ).model_dump(mode="json"),
            "tenant_id": "tenant-a",
            "source_id": "source-a",
            "scope_id": encode_scope_id("tenant-a", "source-a"),
        },
    )
    source_manager = _Manager({"job-source": source_job})
    target_supported = _Manager()
    target_missing = _Manager()
    multi_agent_manager = _MultiAgentManager(
        {
            encode_scope_id("tenant-b", "source-a"): _Workspace(
                target_supported,
            ),
            encode_scope_id("tenant-c", "source-a"): _Workspace(
                target_missing,
            ),
        },
    )
    client = _build_client(
        source_manager,
        multi_agent_manager=multi_agent_manager,
        tenant_workspace_pool=_TenantWorkspacePool(),
    )
    _install_provider_manager(
        {},
        providers_by_tenant={
            encode_scope_id("tenant-b", "source-a"): {
                "openai": _Provider(["gpt-5.4"]),
            },
            encode_scope_id("tenant-c", "source-a"): {
                "anthropic": _Provider(["claude-3-7-sonnet"]),
            },
        },
    )

    response = client.post(
        "/cron/jobs/job-source/broadcast",
        json={"target_tenant_ids": ["tenant-b", "tenant-c"]},
    )

    assert response.status_code == 200
    assert target_supported.created[0].model_slot is not None
    assert target_supported.created[0].model_slot.provider_id == "openai"
    assert target_supported.created[0].model_slot.model == "gpt-5.4"
    assert target_missing.created[0].model_slot is None
    assert target_missing.created[0].meta["broadcast_original_model_slot"] == {
        "provider_id": "openai",
        "model": "gpt-5.4",
    }
    assert (
        target_missing.created[0].meta["broadcast_model_slot_fallback_reason"]
        == "provider_not_found"
    )
    assert response.json()["results"] == [
        {
            "tenant_id": "tenant-b",
            "success": True,
            "job_id": target_supported.created[0].id,
            "cron": target_supported.created[0].schedule.cron,
            "timezone": target_supported.created[0].schedule.timezone,
            "offset_minutes": 0,
            "notification_timezone": "UTC",
            "error": "",
            "warning": "",
        },
        {
            "tenant_id": "tenant-c",
            "success": True,
            "job_id": target_missing.created[0].id,
            "cron": target_missing.created[0].schedule.cron,
            "timezone": target_missing.created[0].schedule.timezone,
            "offset_minutes": 240,
            "notification_timezone": "UTC",
            "error": "",
            "warning": (
                "model_slot not copied: provider/model unavailable in "
                "target tenant"
            ),
        },
    ]


def test_broadcast_persists_model_not_found_reason_for_unsupported_model():
    source_job = CronJobSpec.model_validate(
        {
            **_job_spec(
                "job-source",
                model_slot=_model_slot(),
            ),
            "schedule": ScheduleSpec(
                cron="0 9 * * *",
            ).model_dump(mode="json"),
            "tenant_id": "tenant-a",
            "source_id": "source-a",
            "scope_id": encode_scope_id("tenant-a", "source-a"),
        },
    )
    source_manager = _Manager({"job-source": source_job})
    target_missing = _Manager()
    multi_agent_manager = _MultiAgentManager(
        {
            encode_scope_id("tenant-c", "source-a"): _Workspace(
                target_missing,
            ),
        },
    )
    client = _build_client(
        source_manager,
        multi_agent_manager=multi_agent_manager,
        tenant_workspace_pool=_TenantWorkspacePool(),
    )
    _install_provider_manager(
        {},
        providers_by_tenant={
            encode_scope_id("tenant-c", "source-a"): {
                "openai": _Provider(["gpt-4.1"]),
            },
        },
    )

    response = client.post(
        "/cron/jobs/job-source/broadcast",
        json={"target_tenant_ids": ["tenant-c"]},
    )

    assert response.status_code == 200
    assert target_missing.created[0].model_slot is None
    assert (
        target_missing.created[0].meta["broadcast_model_slot_fallback_reason"]
        == "model_not_found"
    )


def test_broadcast_uses_original_cron_when_offset_shift_is_unsupported():
    source_job = CronJobSpec.model_validate(
        {
            **_job_spec("job-source"),
            "schedule": ScheduleSpec(
                cron="30 1 1 * *",
            ).model_dump(mode="json"),
            "tenant_id": "tenant-a",
            "source_id": "source-a",
            "scope_id": encode_scope_id("tenant-a", "source-a"),
        },
    )
    source_manager = _Manager({"job-source": source_job})
    target_first = _Manager()
    target_fallback = _Manager()
    multi_agent_manager = _MultiAgentManager(
        {
            encode_scope_id("tenant-b", "source-a"): _Workspace(
                target_first,
            ),
            encode_scope_id("tenant-c", "source-a"): _Workspace(
                target_fallback,
            ),
        },
    )
    client = _build_client(
        source_manager,
        multi_agent_manager=multi_agent_manager,
        tenant_workspace_pool=_TenantWorkspacePool(),
    )
    _install_provider_manager(
        {},
        providers_by_tenant={
            encode_scope_id("tenant-b", "source-a"): {},
            encode_scope_id("tenant-c", "source-a"): {},
        },
    )

    response = client.post(
        "/cron/jobs/job-source/broadcast",
        json={"target_tenant_ids": ["tenant-b", "tenant-c"]},
    )

    assert response.status_code == 200
    assert target_first.created[0].schedule.cron == "30 1 1 * *"
    assert target_first.created[0].meta["broadcast_offset_minutes"] == 0
    assert target_fallback.created[0].schedule.cron == "30 1 1 * *"
    assert target_fallback.created[0].meta["broadcast_offset_minutes"] == 0
    fallback_result = response.json()["results"][1]
    assert fallback_result["success"] is True
    assert fallback_result["cron"] == "30 1 1 * *"
    assert fallback_result["offset_minutes"] == 0
    assert fallback_result["warning"] == (
        "cron offset not applied: unsupported cron, using original schedule"
    )


def test_broadcast_clears_stale_fallback_meta_when_source_model_slot_missing():
    source_job = CronJobSpec.model_validate(
        {
            **_job_spec("job-source"),
            "schedule": ScheduleSpec(
                cron="0 9 * * *",
            ).model_dump(mode="json"),
            "tenant_id": "tenant-a",
            "source_id": "source-a",
            "scope_id": encode_scope_id("tenant-a", "source-a"),
            "meta": {
                "broadcast_original_model_slot": {
                    "provider_id": "openai",
                    "model": "gpt-5.4",
                },
                "broadcast_model_slot_fallback_reason": ("provider_not_found"),
            },
        },
    )
    source_manager = _Manager({"job-source": source_job})
    target_supported = _Manager()
    multi_agent_manager = _MultiAgentManager(
        {
            encode_scope_id("tenant-b", "source-a"): _Workspace(
                target_supported,
            ),
        },
    )
    client = _build_client(
        source_manager,
        multi_agent_manager=multi_agent_manager,
        tenant_workspace_pool=_TenantWorkspacePool(),
    )
    _install_provider_manager(
        {},
        providers_by_tenant={
            encode_scope_id("tenant-b", "source-a"): {
                "openai": _Provider(["gpt-5.4"]),
            },
        },
    )

    response = client.post(
        "/cron/jobs/job-source/broadcast",
        json={"target_tenant_ids": ["tenant-b"]},
    )

    assert response.status_code == 200
    assert (
        "broadcast_original_model_slot" not in target_supported.created[0].meta
    )
    assert (
        "broadcast_model_slot_fallback_reason"
        not in target_supported.created[0].meta
    )


def test_broadcast_skips_tenant_that_already_has_source_child_job():
    source_job = CronJobSpec.model_validate(
        {
            **_job_spec("job-source"),
            "schedule": ScheduleSpec(
                cron="0 9 * * *",
            ).model_dump(mode="json"),
            "tenant_id": "tenant-a",
            "source_id": "source-a",
            "scope_id": encode_scope_id("tenant-a", "source-a"),
        },
    )
    existing_child_job = CronJobSpec.model_validate(
        {
            **_job_spec("job-existing-child"),
            "schedule": ScheduleSpec(
                cron="0 9 * * *",
            ).model_dump(mode="json"),
            "tenant_id": "tenant-b",
            "source_id": "source-a",
            "scope_id": encode_scope_id("tenant-b", "source-a"),
            "meta": {
                "broadcast_source_job_id": "job-source",
                "broadcast_offset_minutes": 0,
            },
        },
    )
    source_manager = _Manager({"job-source": source_job})
    target_manager = _Manager({"job-existing-child": existing_child_job})
    multi_agent_manager = _MultiAgentManager(
        {
            encode_scope_id("tenant-b", "source-a"): _Workspace(
                target_manager,
            ),
        },
    )
    client = _build_client(
        source_manager,
        multi_agent_manager=multi_agent_manager,
        tenant_workspace_pool=_TenantWorkspacePool(),
    )
    _install_provider_manager(
        {},
        providers_by_tenant={
            encode_scope_id("tenant-b", "source-a"): {},
        },
    )

    response = client.post(
        "/cron/jobs/job-source/broadcast",
        json={"target_tenant_ids": ["tenant-b"]},
    )

    assert response.status_code == 200
    assert target_manager.created == []
    assert response.json()["results"] == [
        {
            "tenant_id": "tenant-b",
            "success": True,
            "job_id": "job-existing-child",
            "cron": "0 9 * * *",
            "timezone": "UTC",
            "offset_minutes": 0,
            "notification_timezone": "UTC",
            "error": "",
            "warning": (
                "broadcast skipped: target tenant already has child job"
            ),
        },
    ]
