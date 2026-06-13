# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from swe.app.crons import auth_state
from swe.app.routers import auth as auth_router
from swe.config.context import encode_scope_id


@pytest.fixture
def workspace_dir(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(
        auth_state,
        "get_tenant_secrets_dir",
        lambda _tenant: tmp_path / "tenant-secret",
    )
    return workspace


def test_get_cron_auth_file_path_uses_tenant_secret_dir(
    tmp_path,
    monkeypatch,
):
    tenant_dir = tmp_path / "tenant-a"
    tenant_secret = tenant_dir / ".secret"

    monkeypatch.setattr(
        auth_state,
        "get_tenant_secrets_dir",
        lambda _tenant: tenant_secret,
    )

    assert auth_state.get_cron_auth_file_path(tenant_id="tenant-a") == (
        tenant_secret / auth_state.CRON_AUTH_FILE_NAME
    )


def test_save_cron_auth_state_uses_tenant_secret_dir_even_with_workspace_dir(
    tmp_path,
    monkeypatch,
):
    tenant_secret = tmp_path / "tenant-a" / ".secret"
    workspace_dir = tmp_path / "tenant-a" / "workspaces" / "default"

    monkeypatch.setattr(
        auth_state,
        "get_tenant_secrets_dir",
        lambda _tenant: tenant_secret,
    )

    path = auth_state.save_cron_auth_state(
        auth_state.CronAuthState(user_info={"id": 1}),
        tenant_id="tenant-a",
        workspace_dir=workspace_dir,
    )

    assert path == tenant_secret / auth_state.CRON_AUTH_FILE_NAME
    assert path.is_file()


def test_cleanup_cron_auth_except_source_keeps_rmassist_only(tmp_path):
    keep_scope = encode_scope_id("tenant-a", "RMASSIST")
    force_delete_scope = encode_scope_id("tenant-force", "RMASSIST")
    delete_scope = encode_scope_id("tenant-b", "PORTAL")
    legacy_keep = "default_RMASSIST"
    raw_tenant = "tenant-c"

    for tenant_id in (
        keep_scope,
        force_delete_scope,
        delete_scope,
        legacy_keep,
        raw_tenant,
    ):
        secret_dir = tmp_path / tenant_id / ".secret"
        secret_dir.mkdir(parents=True)
        (secret_dir / auth_state.CRON_AUTH_FILE_NAME).write_text(
            "{}",
            encoding="utf-8",
        )
    (tmp_path / "tenant-without-auth").mkdir()

    result = auth_state.cleanup_cron_auth_except_source(
        force_delete_tenant_ids=["tenant-force"],
        working_dir=tmp_path,
    )

    assert set(result.deleted_tenant_ids) == {
        delete_scope,
        force_delete_scope,
        raw_tenant,
    }
    assert set(result.deleted_dirs) == {
        str(tmp_path / delete_scope),
        str(tmp_path / force_delete_scope),
        str(tmp_path / raw_tenant),
    }
    assert result.forced_deleted_tenant_ids == [force_delete_scope]
    assert set(result.kept_tenant_ids) == {legacy_keep, keep_scope}
    assert set(result.missing_tenant_ids) == {"tenant-without-auth"}
    assert (
        tmp_path
        / keep_scope
        / ".secret"
        / auth_state.CRON_AUTH_FILE_NAME
    ).is_file()
    assert (
        tmp_path
        / legacy_keep
        / ".secret"
        / auth_state.CRON_AUTH_FILE_NAME
    ).is_file()
    assert not (
        tmp_path
        / force_delete_scope
        / ".secret"
        / auth_state.CRON_AUTH_FILE_NAME
    ).exists()
    assert not (
        tmp_path
        / delete_scope
        / ".secret"
        / auth_state.CRON_AUTH_FILE_NAME
    ).exists()
    assert not (
        tmp_path
        / raw_tenant
        / ".secret"
        / auth_state.CRON_AUTH_FILE_NAME
    ).exists()


def test_cleanup_cron_auth_except_source_dry_run_does_not_delete(tmp_path):
    delete_scope = encode_scope_id("tenant-b", "PORTAL")
    auth_path = (
        tmp_path / delete_scope / ".secret" / auth_state.CRON_AUTH_FILE_NAME
    )
    auth_path.parent.mkdir(parents=True)
    auth_path.write_text("{}", encoding="utf-8")

    result = auth_state.cleanup_cron_auth_except_source(
        working_dir=tmp_path,
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.deleted_tenant_ids == [delete_scope]
    assert result.deleted_dirs == [str(tmp_path / delete_scope)]
    assert result.forced_deleted_tenant_ids == []
    assert auth_path.is_file()


def test_merge_auth_token_into_cookie_uses_token_when_cookie_is_empty():
    assert auth_state.merge_auth_token_into_cookie("", "new-token") == (
        "com.cmb.dw.rtl.sso.token=new-token"
    )


def test_ensure_user_info_reuses_existing_state_when_not_near_expiry(
    monkeypatch,
    workspace_dir,
):
    state = auth_state.save_user_info_from_access_token(
        "access-1",
        cookie_header="foo=bar; com.cmb.dw.rtl.sso.token=access-1",
        workspace_dir=workspace_dir,
    )
    original_refreshed_at = state.user_info_refreshed_at

    get_user_info_calls: list[str] = []

    def fake_get_user_info(access_token: str):
        get_user_info_calls.append(access_token)
        return {"userInfo": {"token": access_token}, "exp": 1776937265}

    monkeypatch.setattr(auth_state, "get_user_info", fake_get_user_info)

    reused = auth_state.ensure_user_info_from_access_token(
        "access-2",
        cookie_header="foo=bar; com.cmb.dw.rtl.sso.token=access-2",
        workspace_dir=workspace_dir,
    )

    assert get_user_info_calls == []
    assert reused.reused is True
    assert reused.state.user_info == state.user_info
    assert reused.state.user_info_refreshed_at == original_refreshed_at
    assert reused.state.cookie_header == (
        "foo=bar; com.cmb.dw.rtl.sso.token=access-2"
    )


def test_ensure_user_info_refreshes_when_near_expiry(
    monkeypatch,
    workspace_dir,
):
    state = auth_state.save_user_info_from_access_token(
        "access-1",
        cookie_header="foo=bar; com.cmb.dw.rtl.sso.token=access-1",
        workspace_dir=workspace_dir,
    )
    state.user_info_expires_at = auth_state.utc_now() + timedelta(hours=1)
    auth_state.save_cron_auth_state(state, workspace_dir=workspace_dir)

    get_user_info_calls: list[str] = []

    def fake_get_user_info(access_token: str):
        get_user_info_calls.append(access_token)
        return {
            "userInfo": {"token": access_token, "fresh": True},
            "exp": 1776937265,
        }

    monkeypatch.setattr(auth_state, "get_user_info", fake_get_user_info)

    refreshed = auth_state.ensure_user_info_from_access_token(
        "access-2",
        cookie_header="foo=bar; com.cmb.dw.rtl.sso.token=access-2",
        workspace_dir=workspace_dir,
    )

    assert get_user_info_calls == ["access-2"]
    assert refreshed.reused is False
    assert refreshed.state.user_info == {
        "token": "access-2",
        "fresh": True,
    }
    assert refreshed.state.cookie_header == (
        "foo=bar; com.cmb.dw.rtl.sso.token=access-2"
    )


def test_issue_auth_token_persists_plain_auth_token(
    monkeypatch,
    workspace_dir,
):
    auth_state.save_user_info_from_access_token(
        "access-1",
        cookie_header="foo=bar; com.cmb.dw.rtl.sso.token=access-1",
        workspace_dir=workspace_dir,
    )

    captured = {}

    def fake_get_auth_token(user_info):
        captured["user_info"] = user_info
        return "plain-auth-token"

    monkeypatch.setattr(auth_state, "get_auth_token", fake_get_auth_token)

    resolved = auth_state.issue_auth_token(workspace_dir=workspace_dir)
    state = auth_state.load_cron_auth_state(workspace_dir=workspace_dir)

    assert captured["user_info"] == {"value": "access-1"}
    assert resolved.token == "plain-auth-token"
    assert state.auth_token == "plain-auth-token"


def test_resolve_auth_token_for_execution_returns_empty_when_user_info_missing(
    workspace_dir,
):
    resolved = auth_state.resolve_auth_token_for_execution(
        workspace_dir=workspace_dir,
    )

    assert resolved.token is None
    assert resolved.cookie_header is None
    assert resolved.expires_at is None


def test_resolve_auth_token_returns_cookie_for_empty_stored_cookie(
    monkeypatch,
    workspace_dir,
):
    state = auth_state.CronAuthState(
        user_info={"id": 1},
        user_info_expires_at=auth_state.utc_now() + timedelta(hours=1),
        cookie_header="",
    )
    auth_state.save_cron_auth_state(state, workspace_dir=workspace_dir)

    monkeypatch.setattr(
        auth_state,
        "get_auth_token",
        lambda _payload: "auth-123",
    )

    resolved = auth_state.resolve_auth_token_for_execution(
        workspace_dir=workspace_dir,
    )

    assert resolved.cookie_header == "com.cmb.dw.rtl.sso.token=auth-123"


def test_resolve_auth_token_for_execution_includes_cookie_header(
    monkeypatch,
    workspace_dir,
):
    auth_state.save_user_info_from_access_token(
        "access-1",
        cookie_header="foo=bar; com.cmb.dw.rtl.sso.token=access-1; theme=dark",
        workspace_dir=workspace_dir,
    )

    monkeypatch.setattr(
        auth_state,
        "get_auth_token",
        lambda _payload: "auth-123",
    )

    resolved = auth_state.resolve_auth_token_for_execution(
        workspace_dir=workspace_dir,
    )

    assert resolved.token == "auth-123"
    assert resolved.cookie_header == (
        "foo=bar; com.cmb.dw.rtl.sso.token=auth-123; theme=dark"
    )


@pytest.mark.asyncio
async def test_configure_cron_auth_returns_reused_status(monkeypatch):
    async def fake_get_agent_for_request(_request):
        return SimpleNamespace(tenant_id="tenant-a", workspace_dir="/tmp/ws")

    ensured_args = {}

    monkeypatch.setattr(
        auth_router,
        "get_agent_for_request",
        fake_get_agent_for_request,
    )
    monkeypatch.setattr(
        auth_router,
        "extract_access_token_from_cookie",
        lambda cookie: "token-from-cookie",
    )

    def fake_ensure_user_info_from_access_token(*args, **kwargs):
        ensured_args["args"] = args
        ensured_args["kwargs"] = kwargs
        return auth_state.CronUserInfoEnsureResult(
            state=auth_state.CronAuthState(),
            reused=True,
        )

    monkeypatch.setattr(
        auth_router,
        "ensure_user_info_from_access_token",
        fake_ensure_user_info_from_access_token,
    )
    monkeypatch.setattr(
        auth_router,
        "get_auth_snapshot",
        lambda **kwargs: auth_state.CronAuthSnapshot(
            configured=True,
            user_info_expires_at=None,
            auth_token_expires_at=None,
            has_auth_token=False,
        ),
    )

    response = await auth_router.configure_cron_auth(
        auth_router.CronAuthConfigureRequest(
            cookie="foo=bar; com.cmb.dw.rtl.sso.token=token-from-cookie",
        ),
        request=SimpleNamespace(),
    )

    assert response["user_info_status"] == "reused"
    assert ensured_args["args"] == ("token-from-cookie",)
    assert ensured_args["kwargs"]["cookie_header"] == (
        "foo=bar; com.cmb.dw.rtl.sso.token=token-from-cookie"
    )


@pytest.mark.asyncio
async def test_configure_cron_auth_returns_refreshed_status(monkeypatch):
    async def fake_get_agent_for_request(_request):
        return SimpleNamespace(tenant_id="tenant-a", workspace_dir="/tmp/ws")

    monkeypatch.setattr(
        auth_router,
        "get_agent_for_request",
        fake_get_agent_for_request,
    )
    monkeypatch.setattr(
        auth_router,
        "extract_access_token_from_cookie",
        lambda cookie: "token-from-cookie",
    )
    monkeypatch.setattr(
        auth_router,
        "ensure_user_info_from_access_token",
        lambda *args, **kwargs: auth_state.CronUserInfoEnsureResult(
            state=auth_state.CronAuthState(),
            reused=False,
        ),
    )
    monkeypatch.setattr(
        auth_router,
        "get_auth_snapshot",
        lambda **kwargs: auth_state.CronAuthSnapshot(
            configured=True,
            user_info_expires_at=None,
            auth_token_expires_at=None,
            has_auth_token=False,
        ),
    )

    response = await auth_router.configure_cron_auth(
        auth_router.CronAuthConfigureRequest(
            cookie="foo=bar; com.cmb.dw.rtl.sso.token=token-from-cookie",
        ),
        request=SimpleNamespace(),
    )

    assert response["user_info_status"] == "refreshed"


@pytest.mark.asyncio
async def test_cleanup_cron_auth_endpoint_returns_summary(monkeypatch):
    observed = {}

    def fake_cleanup_cron_auth_except_source(**kwargs):
        observed.update(kwargs)
        return auth_state.CronAuthCleanupResult(
            deleted_tenant_ids=["tenant-a"],
            deleted_dirs=["C:/workspace/tenant-a"],
            forced_deleted_tenant_ids=["tenant-a"],
            kept_tenant_ids=["tenant-b"],
            missing_tenant_ids=["tenant-c"],
            dry_run=True,
        )

    monkeypatch.setattr(
        auth_router,
        "cleanup_cron_auth_except_source",
        fake_cleanup_cron_auth_except_source,
    )

    response = await auth_router.cleanup_cron_auth(
        auth_router.CronAuthCleanupRequest(
            dry_run=True,
            force_delete_tenant_ids=["tenant-a"],
        ),
    )

    assert observed == {
        "keep_source_id": "RMASSIST",
        "force_delete_tenant_ids": ["tenant-a"],
        "dry_run": True,
    }
    assert response["deleted_count"] == 1
    assert response["kept_count"] == 1
    assert response["missing_count"] == 1
    assert response["deleted_tenant_ids"] == ["tenant-a"]
    assert response["deleted_dirs"] == ["C:/workspace/tenant-a"]
    assert response["forced_deleted_tenant_ids"] == ["tenant-a"]
    assert response["force_delete_tenant_ids"] == ["tenant-a"]
