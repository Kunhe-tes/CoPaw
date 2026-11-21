# -*- coding: utf-8 -*-
"""新重试接口只认可信 Header，拒绝 Body 注入权限。"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.unit.scheduler.test_managed_cron_callbacks import callback_setup
from tests.unit.scheduler.test_managed_batch_retry import (
    failed_batch,
    retry_body,
)


@pytest.mark.asyncio
async def test_batch_operations_headers_idempotency_and_strict_body(
    callback_setup,
):
    from scheduler.app.routers import managed_batch_operations as api
    from scheduler.app.services.cron.managed.batch_retry import (
        BatchRetryService,
    )

    caller, batch = await failed_batch(callback_setup, category="auth_expired")
    service = BatchRetryService(callback_setup[0])
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.dependency_overrides[api.batch_service] = lambda: service
    headers = {
        "X-User-Id": caller.actor_id,
        "X-Source-Id": caller.source_id,
        "X-User-Role": "manager",
    }
    path = f"/api/scheduler/cron/managed-dispatch/batches/{batch}"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        assert (
            await client.get(
                path + "/failures",
                headers={**headers, "X-User-Role": "user"},
            )
        ).status_code == 403
        assert (
            await client.get(
                path + "/failures",
                headers={**headers, "X-Source-Id": "other"},
            )
        ).status_code == 404
        preview = (
            await client.get(path + "/failures", headers=headers)
        ).json()
        command = retry_body(preview).model_dump()
        assert (
            await client.post(
                path + "/retry",
                headers=headers,
                json={**command, "source_id": "other"},
            )
        ).status_code == 422
        first = await client.post(
            path + "/retry",
            headers=headers,
            json=command,
        )
        assert first.status_code == 200
        assert first.json()["queued"] == 1
        assert (
            await client.post(path + "/retry", headers=headers, json=command)
        ).json()["reused"]
        assert (
            await client.post(
                path + "/retry",
                headers=headers,
                json={**command, "confirm_stopped": True},
            )
        ).status_code == 409


@pytest.mark.asyncio
async def test_failure_preview_can_read_past_200(callback_setup, monkeypatch):
    from scheduler.app.routers import managed_batch_operations as api
    from scheduler.app.services.cron.managed import batch_failures

    db = callback_setup[0]
    caller, batch = await failed_batch(callback_setup, category="auth_expired")
    receipt = await batch_failures.read_batch(db, caller, batch)
    (original,) = await batch_failures.member_rows(db, receipt)

    async def many_members(*_):
        return [
            {
                **original,
                "member_id": "different-category",
                "result_json": '{"failure_type": "configuration"}',
            },
            *(
                {**original, "member_id": f"member-{number}"}
                for number in range(1, 202)
            ),
        ]

    monkeypatch.setattr(batch_failures, "member_rows", many_members)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.batch_service] = (
        lambda: api.BatchRetryService(db)
    )
    headers = {
        "X-User-Id": caller.actor_id,
        "X-Source-Id": caller.source_id,
        "X-User-Role": "manager",
    }
    path = f"/scheduler/cron/managed-dispatch/batches/{batch}/failures"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = (await client.get(path, headers=headers)).json()
        last_response = await client.get(
            path,
            headers=headers,
            params={"offset": 200, "types": "auth_expired"},
        )
        assert last_response.status_code == 200
        last = last_response.json()
        assert (
            await client.get(path, headers=headers, params={"offset": -1})
        ).status_code == 422

    assert len(first["items"]) == 200
    assert first["has_more"]
    assert last["offset"] == 200
    assert [item["member_id"] for item in last["items"]] == ["member-201"]
    assert last["counts"] == first["counts"]
    assert first["matched_count"] == 202
    assert last["matched_count"] == 201
    assert not last["has_more"]
