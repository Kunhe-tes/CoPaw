# -*- coding: utf-8 -*-
"""Internal reload API source-scope regression tests."""

import base64
import json
from types import SimpleNamespace
from unittest.mock import call
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from swe.app.identity_resolver import ResolvedIdentity
from swe.app.routers import internal as internal_router
from swe.app.routers.internal import router
from swe.config.context import encode_scope_id


def _build_client(manager) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.multi_agent_manager = manager
    return TestClient(app)


def test_internal_reload_requires_source_id() -> None:
    manager = SimpleNamespace(reload_agent=AsyncMock(return_value=True))
    client = _build_client(manager)

    response = client.post(
        "/internal/agents/default/reload?tenant_id=tenant-a",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "source_id is required"
    manager.reload_agent.assert_not_called()


def test_internal_reload_resolves_scope_id() -> None:
    manager = SimpleNamespace(reload_agent=AsyncMock(return_value=True))
    client = _build_client(manager)

    response = client.post(
        "/internal/agents/default/reload"
        "?tenant_id=tenant-a&source_id=source-a",
    )

    assert response.status_code == 200
    assert response.json()["tenant_id"] == "tenant-a"
    assert response.json()["scope_id"] == encode_scope_id(
        "tenant-a",
        "source-a",
    )
    manager.reload_agent.assert_awaited_once_with(
        "default",
        tenant_id=encode_scope_id("tenant-a", "source-a"),
    )


def test_internal_reload_rejects_invalid_source_id() -> None:
    manager = SimpleNamespace(reload_agent=AsyncMock(return_value=True))
    client = _build_client(manager)

    response = client.post(
        "/internal/agents/default/reload"
        "?tenant_id=tenant-a&source_id=../bad",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid source_id"
    manager.reload_agent.assert_not_called()


def test_internal_cron_callback_dispatches_job_param_tenant() -> None:
    cron_manager = SimpleNamespace(run_job=AsyncMock())
    manager = SimpleNamespace(
        get_agent=AsyncMock(
            return_value=SimpleNamespace(cron_manager=cron_manager),
        ),
    )
    client = _build_client(manager)
    payload = {
        "tenant_id": "runtime-scope",
        "agent_id": "default",
        "task_type": "job",
        "job_id": "job-1",
    }
    job_param = base64.urlsafe_b64encode(
        json.dumps(payload).encode(),
    ).decode()

    response = client.post(
        "/internal/cron/callback",
        json={"jobParam": job_param},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "task_type": "job"}
    manager.get_agent.assert_awaited_once_with(
        "default",
        tenant_id="runtime-scope",
    )
    cron_manager.run_job.assert_awaited_once_with(
        "job-1",
        is_manual=False,
        source_id=None,
    )


def test_internal_cron_callback_forwards_b3_headers_to_run_job() -> None:
    cron_manager = SimpleNamespace(run_job=AsyncMock())
    manager = SimpleNamespace(
        get_agent=AsyncMock(
            return_value=SimpleNamespace(cron_manager=cron_manager),
        ),
    )
    client = _build_client(manager)

    response = client.post(
        "/internal/cron/callback",
        json={
            "tenant_id": "tenant-a",
            "source_id": "source-a",
            "agent_id": "default",
            "task_type": "job",
            "job_id": "job-1",
        },
        headers={
            "X-B3-Traceid": "8267fd70bacf497704fec30eaa353979",
            "X-B3-Spanid": "32befd146889a61a",
            "X-B3-Parentspanid": "5be42cd2b570b6da",
            "X-B3-Sampled": "1",
            "X-B3-Debug": "0",
            "X-B3-BusinessId": "LQ1303LMES-WEB",
            "X-B3-Timestamp": "1782962021603",
        },
    )

    assert response.status_code == 200
    cron_manager.run_job.assert_awaited_once_with(
        "job-1",
        is_manual=False,
        source_id="source-a",
        dispatch_meta={
            "passthrough_headers": {
                "X-B3-Traceid": "8267fd70bacf497704fec30eaa353979",
                "X-B3-Spanid": "32befd146889a61a",
                "X-B3-Parentspanid": "5be42cd2b570b6da",
                "X-B3-Sampled": "1",
                "X-B3-Debug": "0",
                "X-B3-BusinessId": "LQ1303LMES-WEB",
                "X-B3-Timestamp": "1782962021603",
            },
            "b3_trace_id": "8267fd70bacf497704fec30eaa353979",
        },
    )


def test_internal_cron_callback_skips_batch_parent_external_callback(
    monkeypatch,
) -> None:
    source_job = SimpleNamespace(
        meta={"broadcast_dispatch_intents_enabled": True},
    )
    cron_manager = SimpleNamespace(
        run_job=AsyncMock(),
        get_job=AsyncMock(return_value=source_job),
    )
    manager = SimpleNamespace(
        get_agent=AsyncMock(
            return_value=SimpleNamespace(cron_manager=cron_manager),
        ),
    )

    monkeypatch.setenv("SWE_CRON_DISPATCH_INTENTS_ENABLED", "1")
    client = _build_client(manager)
    payload = {
        "tenant_id": "tenant-a",
        "source_id": "source-a",
        "agent_id": "default",
        "task_type": "job",
        "job_id": "job-1",
    }
    job_param = base64.urlsafe_b64encode(
        json.dumps(payload).encode(),
    ).decode()

    response = client.post(
        "/internal/cron/callback",
        json={"jobParam": job_param},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "task_type": "job",
        "skipped": "batch_managed_external_callback",
    }
    cron_manager.run_job.assert_not_awaited()


def test_internal_cron_callback_skips_batch_parent_direct_external_body(
    monkeypatch,
) -> None:
    source_job = SimpleNamespace(
        meta={"broadcast_dispatch_intents_enabled": True},
        id="job-1",
        schedule=SimpleNamespace(cron="0 9 * * *", timezone="UTC"),
    )
    cron_manager = SimpleNamespace(
        run_job=AsyncMock(),
        get_job=AsyncMock(return_value=source_job),
    )
    manager = SimpleNamespace(
        get_agent=AsyncMock(
            return_value=SimpleNamespace(cron_manager=cron_manager),
        ),
    )

    monkeypatch.setenv("SWE_CRON_DISPATCH_INTENTS_ENABLED", "1")
    client = _build_client(manager)
    body = {
        "tenant_id": "tenant-a",
        "source_id": "source-a",
        "agent_id": "default",
        "task_type": "job",
        "job_id": "job-1",
        "logId": "scheduler-log-1",
    }

    response = client.post("/internal/cron/callback", json=body)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "task_type": "job",
        "skipped": "batch_managed_external_callback",
    }
    cron_manager.run_job.assert_not_awaited()


def test_internal_cron_callback_runs_flagged_parent_when_runtime_flag_off(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SWE_CRON_DISPATCH_INTENTS_ENABLED", raising=False)
    source_job = SimpleNamespace(
        meta={"broadcast_dispatch_intents_enabled": True},
    )
    cron_manager = SimpleNamespace(
        run_job=AsyncMock(),
        get_job=AsyncMock(return_value=source_job),
    )
    manager = SimpleNamespace(
        get_agent=AsyncMock(
            return_value=SimpleNamespace(cron_manager=cron_manager),
        ),
    )
    client = _build_client(manager)

    response = client.post(
        "/internal/cron/callback",
        json={
            "tenant_id": "tenant-a",
            "source_id": "source-a",
            "agent_id": "default",
            "task_type": "job",
            "job_id": "job-1",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "task_type": "job"}
    cron_manager.run_job.assert_awaited_once_with(
        "job-1",
        is_manual=False,
        source_id="source-a",
    )


def test_internal_cron_callback_skips_batch_managed_child_callback(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SWE_CRON_DISPATCH_INTENTS_ENABLED", "1")
    child_job = SimpleNamespace(
        meta={
            "broadcast_source_job_id": "parent-job",
            "broadcast_dispatch_intents_enabled": True,
        },
    )
    cron_manager = SimpleNamespace(
        run_job=AsyncMock(),
        get_job=AsyncMock(return_value=child_job),
    )
    manager = SimpleNamespace(
        get_agent=AsyncMock(
            return_value=SimpleNamespace(cron_manager=cron_manager),
        ),
    )
    client = _build_client(manager)
    payload = {
        "tenant_id": "tenant-b",
        "source_id": "source-a",
        "agent_id": "default",
        "task_type": "job",
        "job_id": "child-1",
    }
    job_param = base64.urlsafe_b64encode(
        json.dumps(payload).encode(),
    ).decode()

    response = client.post(
        "/internal/cron/callback",
        json={"jobParam": job_param},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "task_type": "job",
        "skipped": "batch_managed_child",
    }
    cron_manager.run_job.assert_not_awaited()


def test_dispatch_service_callback_runs_batch_managed_child(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SWE_CRON_DISPATCH_INTENTS_ENABLED", "1")
    child_job = SimpleNamespace(
        meta={
            "broadcast_source_job_id": "parent-job",
            "broadcast_dispatch_intents_enabled": True,
        },
    )
    cron_manager = SimpleNamespace(
        run_job=AsyncMock(),
        get_job=AsyncMock(return_value=child_job),
    )
    manager = SimpleNamespace(
        get_agent=AsyncMock(
            return_value=SimpleNamespace(cron_manager=cron_manager),
        ),
    )
    client = _build_client(manager)

    response = client.post(
        "/internal/cron/callback",
        json={
            "tenant_id": "tenant-b",
            "source_id": "source-a",
            "agent_id": "default",
            "task_type": "job",
            "job_id": "child-1",
            "scopeId": "tenant-b-source-a",
            "fromId": "tenant-b",
            "callback_source": "dispatch_service",
            "dispatch_intent_id": 7,
            "dispatch_batch_id": "batch-1",
            "dispatch_attempt": 2,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "task_type": "job"}
    cron_manager.run_job.assert_awaited_once_with(
        "child-1",
        is_manual=False,
        source_id="source-a",
        dispatch_meta={
            "source": "dispatch_service",
            "intent_id": 7,
            "batch_id": "batch-1",
            "dispatch_attempt": 2,
            "tenant_id": "tenant-b",
            "source_id": "source-a",
            "scope_id": "tenant-b-source-a",
            "from_id": "tenant-b",
            "agent_id": "default",
            "job_id": "child-1",
            "parent_scheduled_fire_at": "",
            "provider_id": "default",
            "model_id": "default",
        },
    )


def test_dispatch_service_callback_rejects_missing_dispatch_identity(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SWE_CRON_DISPATCH_INTENTS_ENABLED", "1")
    child_job = SimpleNamespace(
        meta={
            "broadcast_source_job_id": "parent-job",
            "broadcast_dispatch_intents_enabled": True,
        },
    )
    cron_manager = SimpleNamespace(
        run_job=AsyncMock(),
        get_job=AsyncMock(return_value=child_job),
    )
    manager = SimpleNamespace(
        get_agent=AsyncMock(
            return_value=SimpleNamespace(cron_manager=cron_manager),
        ),
    )
    client = _build_client(manager)

    response = client.post(
        "/internal/cron/callback",
        json={
            "tenant_id": "tenant-b",
            "source_id": "source-a",
            "agent_id": "default",
            "task_type": "job",
            "job_id": "child-1",
            "callback_source": "dispatch_service",
        },
    )

    assert response.status_code == 400
    assert "dispatch_service callback requires" in response.json()["detail"]
    cron_manager.run_job.assert_not_awaited()


def test_internal_scope_encode_single_item() -> None:
    client = _build_client(SimpleNamespace())

    response = client.post(
        "/internal/scope/encode",
        json={"tenant_id": "tenant-a", "source_id": "source-a"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "item": {
            "tenant_id": "tenant-a",
            "source_id": "source-a",
            "scope_id": encode_scope_id("tenant-a", "source-a"),
        },
    }


def test_internal_runtime_tenant_ids_exclude_template_dirs(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        internal_router,
        "list_all_tenant_ids",
        lambda: [
            "default",
            "default_ruice",
            encode_scope_id("tenant-a", "source-a"),
            "tenant-b",
        ],
    )

    assert internal_router._list_runtime_tenant_ids() == [
        "default",
        encode_scope_id("tenant-a", "source-a"),
        "tenant-b",
    ]


def test_internal_scope_encode_skips_internal_token_auth(
    monkeypatch,
) -> None:
    client = _build_client(SimpleNamespace())
    monkeypatch.setattr(internal_router, "_INTERNAL_TOKEN", "secret-token")

    response = client.post(
        "/internal/scope/encode",
        json={"tenant_id": "tenant-a", "source_id": "source-a"},
    )

    assert response.status_code == 200


def test_internal_scope_encode_batch_items() -> None:
    client = _build_client(SimpleNamespace())

    response = client.post(
        "/internal/scope/encode",
        json={
            "items": [
                {"tenant_id": "tenant-a", "source_id": "source-a"},
                {"tenant_id": "tenant-b", "source_id": "source-b"},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "items": [
            {
                "tenant_id": "tenant-a",
                "source_id": "source-a",
                "scope_id": encode_scope_id("tenant-a", "source-a"),
            },
            {
                "tenant_id": "tenant-b",
                "source_id": "source-b",
                "scope_id": encode_scope_id("tenant-b", "source-b"),
            },
        ],
    }


def test_internal_scope_encode_rejects_mixed_single_and_batch_input() -> None:
    client = _build_client(SimpleNamespace())

    response = client.post(
        "/internal/scope/encode",
        json={
            "tenant_id": "tenant-a",
            "source_id": "source-a",
            "items": [
                {"tenant_id": "tenant-b", "source_id": "source-b"},
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Expected either tenant_id/source_id or items"
    )


def test_internal_scope_encode_rejects_empty_fields() -> None:
    client = _build_client(SimpleNamespace())

    response = client.post(
        "/internal/scope/encode",
        json={"tenant_id": "", "source_id": "source-a"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid tenant_id"


def test_internal_scope_encode_rejects_empty_batch() -> None:
    client = _build_client(SimpleNamespace())

    response = client.post(
        "/internal/scope/encode",
        json={"items": []},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "items must not be empty"


def test_internal_scope_decode_single_item() -> None:
    client = _build_client(SimpleNamespace())
    scope_id = encode_scope_id("tenant-a", "source-a")

    response = client.post(
        "/internal/scope/decode",
        json={"scope_id": scope_id},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "item": {
            "scope_id": scope_id,
            "tenant_id": "tenant-a",
            "source_id": "source-a",
        },
    }


def test_internal_scope_decode_skips_internal_token_auth(
    monkeypatch,
) -> None:
    client = _build_client(SimpleNamespace())
    scope_id = encode_scope_id("tenant-a", "source-a")
    monkeypatch.setattr(internal_router, "_INTERNAL_TOKEN", "secret-token")

    response = client.post(
        "/internal/scope/decode",
        json={"scope_id": scope_id},
    )

    assert response.status_code == 200


def test_internal_scope_decode_batch_items() -> None:
    client = _build_client(SimpleNamespace())
    scope_a = encode_scope_id("tenant-a", "source-a")
    scope_b = encode_scope_id("tenant-b", "source-b")

    response = client.post(
        "/internal/scope/decode",
        json={"scope_ids": [scope_a, scope_b]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "items": [
            {
                "scope_id": scope_a,
                "tenant_id": "tenant-a",
                "source_id": "source-a",
            },
            {
                "scope_id": scope_b,
                "tenant_id": "tenant-b",
                "source_id": "source-b",
            },
        ],
    }


def test_internal_scope_decode_rejects_legacy_scope() -> None:
    client = _build_client(SimpleNamespace())

    response = client.post(
        "/internal/scope/decode",
        json={"scope_id": "scope.v1.dGVuYW50LWE.c291cmNlLWE"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Legacy scope IDs are not supported"


def test_internal_scope_decode_rejects_malformed_scope() -> None:
    client = _build_client(SimpleNamespace())

    response = client.post(
        "/internal/scope/decode",
        json={"scope_id": "bad.scope.payload"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid scope_id payload"


def test_internal_batch_initialize_tenants(monkeypatch) -> None:
    pool = SimpleNamespace(ensure_bootstrap=AsyncMock())
    client = _build_client(SimpleNamespace())
    client.app.state.tenant_workspace_pool = pool

    async def fake_resolve_user_identity(**kwargs):
        tenant_id = kwargs["tenant_id"]
        return ResolvedIdentity(
            user_name=f"name-{tenant_id}",
            bbk_id=f"bbk-{tenant_id}",
        )

    monkeypatch.setattr(
        internal_router,
        "resolve_user_identity",
        fake_resolve_user_identity,
    )

    response = client.post(
        "/internal/tenants/batch-initialize",
        json={
            "tenant_ids": "111, 222,111",
            "source_id": "RMASSIST",
            "fail_fast": False,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "total": 2,
        "success_count": 2,
        "fail_count": 0,
        "results": [
            {
                "tenant_id": "111",
                "tenant_name": "name-111",
                "bbk_id": "bbk-111",
                "status": "success",
                "message": "initialized",
            },
            {
                "tenant_id": "222",
                "tenant_name": "name-222",
                "bbk_id": "bbk-222",
                "status": "success",
                "message": "initialized",
            },
        ],
    }
    assert pool.ensure_bootstrap.await_args_list == [
        call(
            "111",
            source_id="RMASSIST",
            tenant_name="name-111",
            bbk_id="bbk-111",
        ),
        call(
            "222",
            source_id="RMASSIST",
            tenant_name="name-222",
            bbk_id="bbk-222",
        ),
    ]


def test_internal_batch_initialize_requires_identity_resolution(
    monkeypatch,
) -> None:
    pool = SimpleNamespace(ensure_bootstrap=AsyncMock())
    client = _build_client(SimpleNamespace())
    client.app.state.tenant_workspace_pool = pool

    async def fake_resolve_user_identity(**kwargs):
        del kwargs
        return ResolvedIdentity(user_name=None, bbk_id=None)

    monkeypatch.setattr(
        internal_router,
        "resolve_user_identity",
        fake_resolve_user_identity,
    )

    response = client.post(
        "/internal/tenants/batch-initialize",
        json={
            "tenant_ids": "111",
            "source_id": "RMASSIST",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "total": 1,
        "success_count": 0,
        "fail_count": 1,
        "results": [
            {
                "tenant_id": "111",
                "tenant_name": None,
                "bbk_id": None,
                "status": "failed",
                "message": "user identity not resolved",
            },
        ],
    }
    pool.ensure_bootstrap.assert_not_awaited()


def test_internal_batch_initialize_marks_existing_tenant_as_skipped(
    monkeypatch,
) -> None:
    pool = SimpleNamespace(ensure_bootstrap=AsyncMock())
    client = _build_client(SimpleNamespace())
    client.app.state.tenant_workspace_pool = pool

    async def fake_resolve_user_identity(**kwargs):
        tenant_id = kwargs["tenant_id"]
        return ResolvedIdentity(
            user_name=f"name-{tenant_id}",
            bbk_id=f"bbk-{tenant_id}",
        )

    async def fake_existing_check(_pool, tenant_id, source_id):
        return tenant_id == "111"

    monkeypatch.setattr(
        internal_router,
        "resolve_user_identity",
        fake_resolve_user_identity,
    )
    monkeypatch.setattr(
        internal_router,
        "_is_tenant_already_bootstrapped",
        fake_existing_check,
    )

    response = client.post(
        "/internal/tenants/batch-initialize",
        json={
            "tenant_ids": "111,222",
            "source_id": "RMASSIST",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "total": 2,
        "success_count": 2,
        "fail_count": 0,
        "results": [
            {
                "tenant_id": "111",
                "tenant_name": "name-111",
                "bbk_id": "bbk-111",
                "status": "success",
                "message": "skipped",
            },
            {
                "tenant_id": "222",
                "tenant_name": "name-222",
                "bbk_id": "bbk-222",
                "status": "success",
                "message": "initialized",
            },
        ],
    }
    pool.ensure_bootstrap.assert_awaited_once_with(
        "222",
        source_id="RMASSIST",
        tenant_name="name-222",
        bbk_id="bbk-222",
    )


def test_internal_batch_initialize_marks_existing_tenant_as_skipped_from_fs(
    tmp_path,
    monkeypatch,
) -> None:
    from swe.app.workspace.tenant_initializer import TenantInitializer

    monkeypatch.setattr(
        TenantInitializer,
        "_has_skill_pool_state",
        lambda self: True,
    )

    existing_init = TenantInitializer(tmp_path, "111", source_id="RMASSIST")
    tenant_dir = existing_init.tenant_dir
    default_workspace = tenant_dir / "workspaces" / "default"
    default_workspace.mkdir(parents=True, exist_ok=True)
    (tenant_dir / "config.json").write_text("{}", encoding="utf-8")
    (default_workspace / "agent.json").write_text("{}", encoding="utf-8")
    (default_workspace / "chats.json").write_text("{}", encoding="utf-8")
    (default_workspace / "jobs.json").write_text("{}", encoding="utf-8")
    (default_workspace / "token_usage.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (default_workspace / "sessions").mkdir(exist_ok=True)
    (default_workspace / "memory").mkdir(exist_ok=True)
    for file_name in (
        "AGENTS.md",
        "HEARTBEAT.md",
        "MEMORY.md",
        "PROFILE.md",
        "SOUL.md",
    ):
        (default_workspace / file_name).write_text("", encoding="utf-8")
    skill_pool_dir = tenant_dir / "skill_pool"
    skill_pool_dir.mkdir(parents=True, exist_ok=True)
    (skill_pool_dir / "skill.json").write_text(
        json.dumps({"skills": {"default-skill": {"name": "default-skill"}}}),
        encoding="utf-8",
    )

    assert existing_init.has_seeded_bootstrap() is True

    pool = SimpleNamespace(
        ensure_bootstrap=AsyncMock(),
        _base_working_dir=tmp_path,
    )
    client = _build_client(SimpleNamespace())
    client.app.state.tenant_workspace_pool = pool

    async def fake_resolve_user_identity(**kwargs):
        tenant_id = kwargs["tenant_id"]
        return ResolvedIdentity(
            user_name=f"name-{tenant_id}",
            bbk_id=f"bbk-{tenant_id}",
        )

    monkeypatch.setattr(
        internal_router,
        "resolve_user_identity",
        fake_resolve_user_identity,
    )

    response = client.post(
        "/internal/tenants/batch-initialize",
        json={
            "tenant_ids": "111",
            "source_id": "RMASSIST",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "total": 1,
        "success_count": 1,
        "fail_count": 0,
        "results": [
            {
                "tenant_id": "111",
                "tenant_name": "name-111",
                "bbk_id": "bbk-111",
                "status": "success",
                "message": "skipped",
            },
        ],
    }
    pool.ensure_bootstrap.assert_not_awaited()


def test_internal_batch_initialize_rejects_empty_tenant_ids() -> None:
    client = _build_client(SimpleNamespace())

    response = client.post(
        "/internal/tenants/batch-initialize",
        json={
            "tenant_ids": " , ",
            "source_id": "RMASSIST",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "tenant_ids must not be empty"
