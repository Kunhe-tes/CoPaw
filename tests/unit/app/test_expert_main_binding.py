# -*- coding: utf-8 -*-
"""Persistent expert identities use repository-wide optimistic concurrency."""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from pydantic import ValidationError

from swe.app.runner.models import ChatSpec
from swe.app.runner.repo.json_repo import JsonChatRepository


def test_binding_update_requires_revision_and_explicit_identity():
    from swe.app.runner.expert_binding import ExpertBindingUpdate

    for payload in (
        {},
        {"expected_revision": 0},
        {"expert_id": None},
        {"expected_revision": -1, "expert_id": None},
        {"expected_revision": 0, "expert_id": None, "fake": 1},
    ):
        with pytest.raises(ValidationError):
            ExpertBindingUpdate.model_validate(payload)
    assert (
        ExpertBindingUpdate(expected_revision=0, expert_id=None).expert_id
        is None
    )


@pytest.mark.asyncio
async def test_binding_compare_and_set_serializes_two_repository_instances(
    tmp_path,
):
    from swe.app.runner.expert_binding import (
        ExpertBindingConflict,
        read_expert_binding,
    )

    path = tmp_path / "chats.json"
    left, right = JsonChatRepository(path), JsonChatRepository(path)
    await left.upsert_chat(ChatSpec(id="chat", session_id="s", user_id="u"))
    results = await asyncio.gather(
        left.compare_and_set_expert_binding("chat", 0, "a"),
        right.compare_and_set_expert_binding("chat", 0, "b"),
        return_exceptions=True,
    )
    assert (
        sum(isinstance(result, ExpertBindingConflict) for result in results)
        == 1
    )
    binding = read_expert_binding(
        await JsonChatRepository(path).get_chat("chat")
    )
    assert binding.revision == 1
    assert binding.expert_id in {"a", "b"}


@pytest.mark.asyncio
async def test_release_revision_prevents_aba_and_stale_generic_updates(
    tmp_path,
):
    from swe.app.runner.expert_binding import (
        ExpertBindingConflict,
        read_expert_binding,
    )

    repo = JsonChatRepository(tmp_path / "chats.json")
    await repo.upsert_chat(ChatSpec(id="chat", session_id="s", user_id="u"))
    stale = await repo.get_chat("chat")
    await repo.compare_and_set_expert_binding("chat", 0, "a")
    await repo.compare_and_set_expert_binding("chat", 1, None)
    await repo.compare_and_set_expert_binding("chat", 2, "a")
    stale.name = "new title"
    stale.meta["ordinary"] = True
    await repo.upsert_chat(stale)
    current = await repo.get_chat("chat")
    assert read_expert_binding(current).model_dump() == {
        "revision": 3,
        "expert_id": "a",
    }
    assert current.name == "new title" and current.meta["ordinary"] is True
    with pytest.raises(ExpertBindingConflict):
        await repo.compare_and_set_expert_binding("chat", 1, "b")


@pytest.mark.asyncio
async def test_plan_transition_atomically_releases_binding_and_rejects_rebind(
    tmp_path,
):
    from swe.app.runner.expert_binding import (
        ExpertBindingModeConflict,
        read_expert_binding,
    )

    repo = JsonChatRepository(tmp_path / "chats.json")
    await repo.upsert_chat(ChatSpec(id="chat", session_id="s", user_id="u"))
    await repo.compare_and_set_expert_binding("chat", 0, "a")
    chat = await repo.get_chat("chat")
    chat.meta["plan_mode_enabled"] = True
    await repo.upsert_chat(chat)
    current = await repo.get_chat("chat")
    assert read_expert_binding(current).model_dump() == {
        "revision": 2,
        "expert_id": None,
    }
    with pytest.raises(ExpertBindingModeConflict):
        await repo.compare_and_set_expert_binding("chat", 2, "b")


@pytest.mark.asyncio
async def test_missing_chat_cannot_be_created_by_binding_update(tmp_path):
    repo = JsonChatRepository(tmp_path / "chats.json")
    with pytest.raises(KeyError):
        await repo.compare_and_set_expert_binding("missing", 0, "a")


@pytest.fixture
def binding_api(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from swe.app.runner import api
    from swe.app.runner.manager import ChatManager

    repo = JsonChatRepository(tmp_path / "chats.json")
    asyncio.run(
        repo.upsert_chat(
            ChatSpec(
                id="chat",
                session_id="s",
                user_id="alice",
                meta={"source_id": "source-a", "agent_id": "profile-a"},
            )
        )
    )
    manager = ChatManager(repo=repo)
    workspace = SimpleNamespace(
        chat_manager=manager,
        workspace_dir=tmp_path,
        tenant_id="alice",
        agent_id="profile-a",
    )
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_chat_manager] = lambda: manager
    app.dependency_overrides[api.get_workspace] = lambda: workspace

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.user_id = request.headers.get("user", "alice")
        request.state.source_id = request.headers.get("source", "source-a")
        request.state.agent_id = request.headers.get("agent", "profile-a")
        request.state.source_system_config = {
            "feature_switches": {
                "expert_as_main_enabled": request.headers.get(
                    "enabled", "true"
                )
                == "true"
            }
        }
        return await call_next(request)

    from swe.app.runner import expert_binding

    monkeypatch.setattr(
        expert_binding,
        "resolve_bound_expert",
        lambda *args: SimpleNamespace(name="Expert A", enabled=True),
    )
    monkeypatch.setattr(
        api, "resolve_bound_expert", expert_binding.resolve_bound_expert
    )
    return TestClient(app), repo


def test_binding_api_preserves_revision_and_syncs_conflicts(binding_api):
    client, _ = binding_api
    assert client.get("/chats/chat/expert-binding").json()["revision"] == 0
    saved = client.put(
        "/chats/chat/expert-binding",
        json={"expected_revision": 0, "expert_id": "a"},
    )
    assert saved.status_code == 200 and saved.json()["revision"] == 1
    conflict = client.put(
        "/chats/chat/expert-binding",
        json={"expected_revision": 0, "expert_id": "b"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["expert_binding"]["expert_id"] == "a"
    disabled = client.get(
        "/chats/chat/expert-binding", headers={"enabled": "false"}
    )
    assert (
        disabled.json()["expert_id"] is None
        and disabled.json()["revision"] == 2
    )
    assert client.get("/chats/chat/expert-binding").json()["expert_id"] is None


@pytest.mark.parametrize(
    "headers",
    [{"user": "bob"}, {"source": "source-b"}, {"agent": "profile-b"}],
)
def test_binding_api_checks_all_chat_scope_dimensions(binding_api, headers):
    client, _ = binding_api
    assert (
        client.get("/chats/chat/expert-binding", headers=headers).status_code
        == 404
    )


def test_generic_api_cannot_inject_binding(binding_api):
    client, _ = binding_api
    response = client.put(
        "/chats/chat",
        json={
            "meta": {"expert_main_binding": {"revision": 2, "expert_id": "a"}}
        },
    )
    assert response.status_code == 400


def test_binding_update_rejects_blank_id_and_non_integer_revision():
    from swe.app.runner.expert_binding import ExpertBindingUpdate

    for payload in (
        {"expected_revision": 0, "expert_id": ""},
        {"expected_revision": 0, "expert_id": "  "},
        {"expected_revision": True, "expert_id": None},
        {"expected_revision": 0.0, "expert_id": None},
    ):
        with pytest.raises(ValidationError):
            ExpertBindingUpdate.model_validate(payload)


@pytest.mark.asyncio
async def test_release_current_binding_releases_winner_after_revision_race(
    tmp_path,
):
    from swe.app.runner.expert_binding import read_expert_binding

    repo = JsonChatRepository(tmp_path / "chats.json")
    await repo.upsert_chat(ChatSpec(id="chat", session_id="s", user_id="u"))
    await repo.compare_and_set_expert_binding("chat", 0, "a")
    await repo.compare_and_set_expert_binding("chat", 1, "b")
    released = await repo.release_current_expert_binding("chat")
    assert released.model_dump() == {"revision": 3, "expert_id": None}
    assert read_expert_binding(await repo.get_chat("chat")) == released


@pytest.mark.asyncio
async def test_update_chat_returns_authoritative_released_binding(tmp_path):
    from swe.app.runner.expert_binding import read_expert_binding
    from swe.app.runner.manager import ChatManager

    repo = JsonChatRepository(tmp_path / "chats.json")
    manager = ChatManager(repo=repo)
    await manager.create_chat(ChatSpec(id="chat", session_id="s", user_id="u"))
    await manager.compare_and_set_expert_binding("chat", 0, "a")
    chat = await manager.get_chat("chat")
    chat.meta["plan_mode_enabled"] = True
    returned = await manager.update_chat(chat)
    assert read_expert_binding(returned).model_dump() == {
        "revision": 2,
        "expert_id": None,
    }


@pytest.mark.asyncio
async def test_update_chat_does_not_recreate_concurrently_deleted_chat(
    tmp_path,
):
    from swe.app.runner.manager import ChatManager

    repo = JsonChatRepository(tmp_path / "chats.json")
    manager = ChatManager(repo=repo)
    await manager.create_chat(ChatSpec(id="chat", session_id="s", user_id="u"))
    update = repo.update_chat_if_exists

    async def delete_before_commit(spec):
        await repo.delete_chats([spec.id])
        return await update(spec)

    repo.update_chat_if_exists = delete_before_commit
    stale = await repo.get_chat("chat")
    with pytest.raises(KeyError):
        await manager.update_chat(stale)
    assert await repo.get_chat("chat") is None


def test_binding_api_does_not_allow_empty_expert_id(binding_api):
    client, _ = binding_api
    response = client.put(
        "/chats/chat/expert-binding",
        json={"expected_revision": 0, "expert_id": ""},
    )
    assert response.status_code == 422


def test_disabled_binding_get_only_reports_an_actual_release(binding_api):
    client, _ = binding_api
    headers = {"enabled": "false"}
    untouched = client.get("/chats/chat/expert-binding", headers=headers)
    assert untouched.json()["reason"] is None
    client.put(
        "/chats/chat/expert-binding",
        json={"expected_revision": 0, "expert_id": "a"},
    )
    released = client.get("/chats/chat/expert-binding", headers=headers)
    assert released.json()["reason"] == "expert_main_disabled"
    assert released.json()["expert_id"] is None
    assert (
        client.get("/chats/chat/expert-binding", headers=headers).json()[
            "reason"
        ]
        is None
    )


def test_disabled_binding_get_releases_binding_after_stale_unbound_read(
    binding_api, monkeypatch
):
    from swe.app.runner import api

    client, repo = binding_api
    original = api.expert_main_enabled_for_request

    async def bind_after_chat_read(request):
        await repo.compare_and_set_expert_binding("chat", 0, "a")
        return await original(request)

    monkeypatch.setattr(
        api, "expert_main_enabled_for_request", bind_after_chat_read
    )
    response = client.get(
        "/chats/chat/expert-binding", headers={"enabled": "false"}
    )
    assert response.json()["expert_id"] is None
    assert response.json()["revision"] == 2
    assert response.json()["reason"] == "expert_main_disabled"


def test_binding_cas_serializes_two_independent_local_processes(tmp_path):
    from swe.app.runner.expert_binding import read_expert_binding

    path = tmp_path / "chats.json"
    asyncio.run(
        JsonChatRepository(path).upsert_chat(
            ChatSpec(id="chat", session_id="s", user_id="u")
        )
    )
    script = """
import asyncio, json, pathlib, sys, time
from swe.app.runner.expert_binding import ExpertBindingConflict
from swe.app.runner.repo.json_repo import JsonChatRepository
path, identity, gate, ready = sys.argv[1:]
repo = JsonChatRepository(pathlib.Path(path))
pathlib.Path(ready).touch()
deadline = time.monotonic() + 15
while not pathlib.Path(gate).exists():
    if time.monotonic() >= deadline:
        raise TimeoutError("CAS gate did not open")
    time.sleep(0.01)
async def run():
    try:
        binding = await repo.compare_and_set_expert_binding(
            "chat", 0, identity
        )
        return {"status": "saved", "binding": binding.model_dump()}
    except ExpertBindingConflict as exc:
        return {"status": "conflict", "binding": exc.binding.model_dump()}
print(json.dumps(asyncio.run(run())))
"""
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src"),
    }
    gate = tmp_path / "go"
    processes = []
    try:
        for identity in ("a", "b"):
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        script,
                        str(path),
                        identity,
                        str(gate),
                        str(tmp_path / identity),
                    ],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        deadline = time.monotonic() + 15
        while not all(
            (tmp_path / identity).exists() for identity in ("a", "b")
        ):
            assert (
                time.monotonic() < deadline
            ), "CAS contenders did not become ready"
            assert all(process.poll() is None for process in processes)
            time.sleep(0.01)
        gate.touch()
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, stderr
            results.append(json.loads(stdout.splitlines()[-1]))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
    assert sorted(result["status"] for result in results) == [
        "conflict",
        "saved",
    ]
    binding = read_expert_binding(
        asyncio.run(JsonChatRepository(path).get_chat("chat"))
    )
    assert binding.revision == 1
    assert binding.expert_id in {"a", "b"}
    assert all(result["binding"] == binding.model_dump() for result in results)


def test_binding_api_retries_release_if_another_tab_wins(
    binding_api, monkeypatch
):
    from swe.app.runner.manager import ChatManager

    client, _ = binding_api
    client.put(
        "/chats/chat/expert-binding",
        json={"expected_revision": 0, "expert_id": "a"},
    )
    original = ChatManager.release_current_expert_binding
    raced = False

    async def competing_binding(self, chat_id):
        nonlocal raced
        if not raced:
            raced = True
            await self.compare_and_set_expert_binding(chat_id, 1, "b")
        return await original(self, chat_id)

    monkeypatch.setattr(
        ChatManager, "release_current_expert_binding", competing_binding
    )
    response = client.get(
        "/chats/chat/expert-binding", headers={"enabled": "false"}
    )
    assert response.json()["expert_id"] is None
    assert response.json()["reason"] == "expert_main_disabled"


def test_binding_put_clears_delayed_save_after_source_disables(
    binding_api, monkeypatch
):
    from swe.app.runner import api
    from swe.app.runner.expert_binding import read_expert_binding

    client, repo = binding_api
    checks = iter([True, False])

    async def source_state(_request):
        return next(checks)

    monkeypatch.setattr(api, "expert_main_enabled_for_request", source_state)
    response = client.put(
        "/chats/chat/expert-binding",
        json={"expected_revision": 0, "expert_id": "a"},
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "expert_main_disabled"
    assert detail["expert_binding"]["expert_id"] is None
    assert (
        read_expert_binding(asyncio.run(repo.get_chat("chat"))).expert_id
        is None
    )


@pytest.mark.parametrize("method", ["binding_put", "binding_get", "chat_put"])
def test_delete_race_returns_404_without_recreating_chat(
    binding_api, monkeypatch, method
):
    from swe.app.runner.manager import ChatManager

    client, repo = binding_api
    if method == "chat_put":
        original = repo.update_chat_if_exists

        async def delete_during_update(spec):
            await repo.delete_chats([spec.id])
            return await original(spec)

        monkeypatch.setattr(
            repo, "update_chat_if_exists", delete_during_update
        )
        response = client.put("/chats/chat", json={"name": "new"})
    elif method == "binding_put":
        original = ChatManager.compare_and_set_expert_binding

        async def delete_before_cas(self, chat_id, revision, expert_id):
            await repo.delete_chats([chat_id])
            return await original(self, chat_id, revision, expert_id)

        monkeypatch.setattr(
            ChatManager, "compare_and_set_expert_binding", delete_before_cas
        )
        response = client.put(
            "/chats/chat/expert-binding",
            json={"expected_revision": 0, "expert_id": "a"},
        )
    else:
        asyncio.run(repo.compare_and_set_expert_binding("chat", 0, "a"))
        original = ChatManager.release_current_expert_binding

        async def delete_before_release(self, chat_id):
            await repo.delete_chats([chat_id])
            return await original(self, chat_id)

        monkeypatch.setattr(
            ChatManager,
            "release_current_expert_binding",
            delete_before_release,
        )
        response = client.get(
            "/chats/chat/expert-binding", headers={"enabled": "false"}
        )
    assert response.status_code == 404
    assert asyncio.run(repo.get_chat("chat")) is None
