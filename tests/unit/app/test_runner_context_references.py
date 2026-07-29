# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _write_skill(workspace: Path, name: str) -> None:
    skill_dir = workspace / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Selected guidance\n---\nbody\n",
        encoding="utf-8",
    )


def test_normalize_context_references_preserves_order_and_deduplicates() -> (
    None
):
    from swe.app.runner.context_references import (
        _normalize_context_references,
    )

    assert _normalize_context_references(
        [
            {"type": "skill", "id": "skill:chosen", "name": "chosen"},
            {"type": "skill", "id": "skill:chosen", "name": "chosen"},
            {"type": "mcp_tool", "id": "mcp_tool:docs/search"},
        ],
    ) == [
        ("skill", {"type": "skill", "id": "skill:chosen", "name": "chosen"}),
        ("mcp_tool", {"type": "mcp_tool", "id": "mcp_tool:docs/search"}),
    ]


@pytest.mark.asyncio
async def test_context_reference_directives_skip_mcp_discovery_without_mcp_reference(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import context_references

    discover = AsyncMock(return_value=[])
    monkeypatch.setattr(context_references, "discover_mcp_tools", discover)

    directives = await context_references.build_context_reference_directives(
        workspace_dir=tmp_path,
        channel="console",
        agent_config=SimpleNamespace(mcp=None),
        references=[
            {
                "type": "workspace_file",
                "id": "workspace_file:media/missing.txt",
                "root": "media",
                "relative_path": "missing.txt",
            },
        ],
    )

    assert directives == []
    discover.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_context_reference_directives_validates_and_deduplicates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app import context_references as directory
    from swe.app.runner import context_references
    from swe.app.runner import skill_selection

    _write_skill(tmp_path, "chosen")
    media = tmp_path / "media"
    media.mkdir()
    (media / "report.txt").write_text("private file content", encoding="utf-8")
    monkeypatch.setattr(
        skill_selection,
        "resolve_effective_skills",
        lambda _workspace, _channel: ["chosen"],
    )

    async def discover_mcp_tools(**_kwargs):
        return [
            directory.MCPToolContextReference(
                id=directory.build_mcp_tool_reference_id("docs", "search"),
                server="docs",
                name="search",
                label="docs / search",
                description="Search docs",
            ),
        ]

    monkeypatch.setattr(
        context_references,
        "discover_mcp_tools",
        discover_mcp_tools,
    )

    references = [
        {"type": "skill", "id": "skill:chosen", "name": "chosen"},
        {"type": "skill", "id": "skill:chosen", "name": "chosen"},
        {
            "type": "mcp_tool",
            "id": directory.build_mcp_tool_reference_id("docs", "search"),
            "server": "docs",
            "name": "search",
        },
        {
            "type": "workspace_file",
            "id": "workspace_file:media/report.txt",
            "root": "media",
            "relative_path": "report.txt",
        },
        {
            "type": "workspace_file",
            "id": "workspace_file:media/../static/secret.txt",
            "root": "media",
            "relative_path": "../static/secret.txt",
        },
        {
            "type": "mcp_tool",
            "id": directory.build_mcp_tool_reference_id("offline", "search"),
            "server": "offline",
            "name": "search",
        },
    ]

    directives = await context_references.build_context_reference_directives(
        workspace_dir=tmp_path,
        channel="console",
        agent_config=SimpleNamespace(mcp=SimpleNamespace(clients={})),
        references=references,
    )

    rendered = [directive.render() for directive in directives]
    assert len(rendered) == 3
    assert any("<SKILL-USE>" in value for value in rendered)
    assert any("<TOOL-PREFERENCE>" in value for value in rendered)
    assert any("<FILE-REFERENCE>" in value for value in rendered)
    assert "private file content" not in "\n".join(rendered)
    assert str((media / "report.txt").resolve()) in "\n".join(rendered)


@pytest.mark.asyncio
async def test_context_reference_file_validation_rejects_missing_and_symlink_escape(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import context_references

    media = tmp_path / "media"
    media.mkdir()
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    (media / "escape.txt").symlink_to(outside / "secret.txt")

    async def discover_mcp_tools(**_kwargs):
        return []

    monkeypatch.setattr(
        context_references,
        "discover_mcp_tools",
        discover_mcp_tools,
    )

    directives = await context_references.build_context_reference_directives(
        workspace_dir=tmp_path,
        channel="console",
        agent_config=SimpleNamespace(mcp=None),
        references=[
            {
                "type": "workspace_file",
                "id": "workspace_file:media/missing.txt",
                "root": "media",
                "relative_path": "missing.txt",
            },
            {
                "type": "workspace_file",
                "id": "workspace_file:media/escape.txt",
                "root": "media",
                "relative_path": "escape.txt",
            },
        ],
    )

    assert directives == []


@pytest.mark.asyncio
async def test_context_reference_resolution_caps_input_and_rejects_oversized_fields(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import context_references

    media = tmp_path / "media"
    media.mkdir()
    references = []
    for index in range(13):
        name = f"report-{index}.txt"
        (media / name).write_text("metadata only", encoding="utf-8")
        references.append(
            {
                "type": "workspace_file",
                "id": f"workspace_file:media/{name}",
                "root": "media",
                "relative_path": name,
            },
        )
    references.insert(
        0,
        {
            "type": "skill",
            "id": f"skill:{'x' * 1_000}",
            "name": "x" * 1_000,
        },
    )

    async def discover_mcp_tools(**_kwargs):
        return []

    monkeypatch.setattr(
        context_references,
        "discover_mcp_tools",
        discover_mcp_tools,
    )

    directives = await context_references.build_context_reference_directives(
        workspace_dir=tmp_path,
        channel="console",
        agent_config=SimpleNamespace(mcp=None),
        references=references,
    )

    assert len(directives) == 11
