# -*- coding: utf-8 -*-
"""验证复制到静态目录工具返回可访问的公开链接。"""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

import swe.app._app as app_module
import swe.constant as constant_module
from swe.agents.tools.copy_file_to_static import copy_file_to_static
from swe.app.agent_context import set_current_agent_id
from swe.config.context import (
    encode_scope_id,
    get_current_file_url_network,
    reset_current_file_url_network,
    reset_current_scope_id,
    reset_current_source_id,
    reset_current_user_id,
    reset_current_workspace_dir,
    resolve_file_url_base,
    set_current_file_url_network,
    set_current_scope_id,
    set_current_source_id,
    set_current_user_id,
    set_current_workspace_dir,
)


def _tool_payload(response):
    return json.loads(response.content[0]["text"])


def _extract_markdown_url(markdown: str) -> str:
    match = re.search(r"\]\((?P<url>[^)]+)\)", markdown)
    assert match is not None
    return match.group("url")


@pytest.mark.asyncio
async def test_copy_file_to_static_returns_scope_static_url(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "report.html"
    source_file.write_text("<p>ok</p>", encoding="utf-8")
    scope_id = encode_scope_id("alice", "portal")
    workspace_dir = tmp_path / scope_id / "workspaces" / "agent-a"
    monkeypatch.setenv("FILE_URL", "https://files.example/")
    set_current_agent_id("agent-a")

    user_token = set_current_user_id("alice")
    source_token = set_current_source_id("portal")
    scope_token = set_current_scope_id(scope_id)
    workspace_token = set_current_workspace_dir(workspace_dir)
    try:
        response = await copy_file_to_static(str(source_file))
    finally:
        reset_current_workspace_dir(workspace_token)
        reset_current_scope_id(scope_token)
        reset_current_source_id(source_token)
        reset_current_user_id(user_token)
        set_current_agent_id("default")

    payload = _tool_payload(response)

    assert payload["ok"] is True
    assert (workspace_dir / "static" / "report.html").read_text(
        encoding="utf-8",
    ) == "<p>ok</p>"
    assert re.search(
        rf"\(https://files\.example/static/{re.escape(scope_id)}/agent-a/"
        r"report\.html\)",
        payload["path"],
    )
    monkeypatch.setattr(constant_module, "WORKING_DIR", tmp_path)
    public_url = _extract_markdown_url(payload["path"])

    with TestClient(
        app_module.app,
        raise_server_exceptions=False,
    ) as client:
        response = client.get(urlparse(public_url).path)

    assert response.status_code == 200
    assert response.text == "<p>ok</p>"


def test_resolve_file_url_base_defaults_to_office(monkeypatch) -> None:
    monkeypatch.delenv("FILE_URL_OFFICE", raising=False)
    monkeypatch.delenv("FILE_URL_BUSINESS", raising=False)
    monkeypatch.setenv("FILE_URL", "https://legacy.example/")

    base_url, network = resolve_file_url_base(None)

    assert base_url == "https://legacy.example"
    assert network == "office"


def test_resolve_file_url_base_uses_business_when_configured(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FILE_URL_OFFICE", "https://office.example/")
    monkeypatch.setenv("FILE_URL_BUSINESS", "https://business.example/")

    base_url, network = resolve_file_url_base("business")

    assert base_url == "https://business.example"
    assert network == "business"


def test_resolve_file_url_base_falls_back_to_office_for_invalid_network(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FILE_URL_OFFICE", "https://office.example/")
    monkeypatch.setenv("FILE_URL_BUSINESS", "https://business.example/")

    base_url, network = resolve_file_url_base("invalid")

    assert base_url == "https://office.example"
    assert network == "office"


def test_resolve_file_url_base_falls_back_to_office_when_business_missing(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FILE_URL_OFFICE", "https://office.example/")
    monkeypatch.delenv("FILE_URL_BUSINESS", raising=False)

    base_url, network = resolve_file_url_base("business")

    assert base_url == "https://office.example"
    assert network == "office"


@pytest.mark.asyncio
async def test_copy_file_to_static_returns_business_url_from_context(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "report.html"
    source_file.write_text("<p>business</p>", encoding="utf-8")
    scope_id = encode_scope_id("alice", "portal")
    workspace_dir = tmp_path / scope_id / "workspaces" / "agent-a"
    monkeypatch.setenv("FILE_URL_OFFICE", "https://office.example/")
    monkeypatch.setenv("FILE_URL_BUSINESS", "https://business.example/")
    set_current_agent_id("agent-a")

    user_token = set_current_user_id("alice")
    source_token = set_current_source_id("portal")
    scope_token = set_current_scope_id(scope_id)
    workspace_token = set_current_workspace_dir(workspace_dir)
    network_token = set_current_file_url_network("business")
    try:
        response = await copy_file_to_static(str(source_file))
    finally:
        reset_current_file_url_network(network_token)
        reset_current_workspace_dir(workspace_token)
        reset_current_scope_id(scope_token)
        reset_current_source_id(source_token)
        reset_current_user_id(user_token)
        set_current_agent_id("default")

    payload = _tool_payload(response)

    assert payload["ok"] is True
    assert payload["url"].startswith(
        f"https://business.example/static/{scope_id}/agent-a/",
    )
    assert payload["network"] == "business"
    assert payload["path"] == f"![report.html]({payload['url']})"
    assert get_current_file_url_network() == "office"


@pytest.mark.asyncio
async def test_copy_file_to_static_recovers_duplicated_static_url_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    scope_id = encode_scope_id("alice", "portal")
    workspace_dir = tmp_path / scope_id / "workspaces" / "agent-a"
    static_dir = workspace_dir / "static"
    static_dir.mkdir(parents=True)
    existing_file = static_dir / "report.html"
    existing_file.write_text("<p>already static</p>", encoding="utf-8")
    mistaken_file_path = static_dir / scope_id / "agent-a" / "report.html"
    monkeypatch.setenv("FILE_URL", "https://files.example/")
    set_current_agent_id("agent-a")

    user_token = set_current_user_id("alice")
    source_token = set_current_source_id("portal")
    scope_token = set_current_scope_id(scope_id)
    workspace_token = set_current_workspace_dir(workspace_dir)
    try:
        response = await copy_file_to_static(str(mistaken_file_path))
    finally:
        reset_current_workspace_dir(workspace_token)
        reset_current_scope_id(scope_token)
        reset_current_source_id(source_token)
        reset_current_user_id(user_token)
        set_current_agent_id("default")

    payload = _tool_payload(response)

    assert payload["ok"] is True
    assert payload["url"].endswith("/report.html")
    assert not (static_dir / "report_1.html").exists()


@pytest.mark.asyncio
async def test_copy_file_to_static_accepts_directory_with_single_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    scope_id = encode_scope_id("alice", "portal")
    workspace_dir = tmp_path / scope_id / "workspaces" / "agent-a"
    export_dir = workspace_dir / "exports"
    export_dir.mkdir(parents=True)
    (export_dir / "single.html").write_text("<p>one</p>", encoding="utf-8")
    monkeypatch.setenv("FILE_URL", "https://files.example/")
    set_current_agent_id("agent-a")

    user_token = set_current_user_id("alice")
    source_token = set_current_source_id("portal")
    scope_token = set_current_scope_id(scope_id)
    workspace_token = set_current_workspace_dir(workspace_dir)
    try:
        response = await copy_file_to_static(str(export_dir))
    finally:
        reset_current_workspace_dir(workspace_token)
        reset_current_scope_id(scope_token)
        reset_current_source_id(source_token)
        reset_current_user_id(user_token)
        set_current_agent_id("default")

    payload = _tool_payload(response)

    assert payload["ok"] is True
    assert (workspace_dir / "static" / "single.html").read_text(
        encoding="utf-8",
    ) == "<p>one</p>"
    assert payload["url"].endswith("/single.html")
