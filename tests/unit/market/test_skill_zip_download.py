# -*- coding: utf-8 -*-
"""技能 ZIP 打包 helper 与下载路由测试。"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from market.app.routers.skill_versions import router as version_router
from market.app.routers.skills_browse import router
from market.marketplace.fs import get_user_skills_dir
from market.marketplace.zip_download import (
    build_skill_zip,
    sanitize_zip_filename,
)


def _create_skill_tree(skill_dir: Path) -> None:
    """创建用于打包测试的最小技能目录。"""
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
    (skill_dir / "skill.json").write_text(
        '{"name":"demo"}\n',
        encoding="utf-8",
    )
    (skill_dir / "references" / "guide.md").write_text(
        "guide content\n",
        encoding="utf-8",
    )


def test_build_skill_zip_creates_zip_file(tmp_path: Path) -> None:
    """应生成可读取的 zip 文件。"""
    skill_dir = tmp_path / "demo_skill"
    skill_dir.mkdir()
    _create_skill_tree(skill_dir)

    zip_path = build_skill_zip(
        skill_dir=skill_dir,
        output_name="demo-skill.zip",
        temp_dir=tmp_path / "artifacts",
    )

    assert zip_path.exists()
    assert zip_path.suffix == ".zip"
    with zipfile.ZipFile(zip_path) as zip_file:
        assert zip_file.read("SKILL.md").decode("utf-8") == "# Demo Skill\n"


def test_build_skill_zip_keeps_relative_paths(tmp_path: Path) -> None:
    """zip 内应保留技能目录下的相对路径结构，并屏蔽 skill.json。"""
    skill_dir = tmp_path / "demo_skill"
    skill_dir.mkdir()
    _create_skill_tree(skill_dir)

    zip_path = build_skill_zip(
        skill_dir=skill_dir,
        output_name="demo-skill.zip",
        temp_dir=tmp_path / "artifacts",
    )

    with zipfile.ZipFile(zip_path) as zip_file:
        assert sorted(zip_file.namelist()) == [
            "SKILL.md",
            "references/guide.md",
        ]
        assert "skill.json" not in zip_file.namelist()


def test_sanitize_zip_filename_replaces_invalid_chars() -> None:
    """应替换非法字符并补齐 zip 后缀。"""
    assert sanitize_zip_filename(" skill:/demo?name ") == "skill_demo_name.zip"


class FakeMarketplace:
    """提供下载路由所需的最小 marketplace 假对象。"""

    def __init__(self, swe_root: Path) -> None:
        self.swe_root = swe_root
        self.marketplace_root = swe_root / "marketplace"
        self.get_my_skills = AsyncMock()
        self.get_skill_detail = AsyncMock()


@pytest.fixture
def test_app(tmp_path: Path) -> FastAPI:
    """创建仅挂载技能浏览路由的测试应用。"""
    app = FastAPI()
    app.state.marketplace = FakeMarketplace(tmp_path)
    app.include_router(router)
    app.include_router(version_router)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """创建测试客户端。"""
    return TestClient(test_app)


def _create_my_skill(
    swe_root: Path,
    user_id: str,
    source_id: str,
    skill_name: str,
) -> Path:
    """在用户技能目录下创建一个最小技能。"""
    skill_dir = (
        get_user_skills_dir(swe_root, user_id, "default", source_id)
        / skill_name
    )
    skill_dir.mkdir(parents=True)
    _create_skill_tree(skill_dir)
    return skill_dir


def _create_market_skill(
    marketplace_root: Path,
    source_id: str,
    item_id: str,
) -> Path:
    """创建市场当前版本技能目录。"""
    skill_dir = marketplace_root / source_id / "skills" / item_id
    skill_dir.mkdir(parents=True)
    _create_skill_tree(skill_dir)
    return skill_dir


def _create_market_skill_version(
    marketplace_root: Path,
    source_id: str,
    item_id: str,
    version_id: str,
    skill_name: str = "demo_skill",
) -> Path:
    """创建市场历史版本快照目录。"""
    versions_root = marketplace_root / source_id / "skill_versions" / item_id
    version_dir = versions_root / version_id
    version_dir.mkdir(parents=True)
    _create_skill_tree(version_dir)
    (versions_root / "versions.json").write_text(
        json.dumps(
            {
                "skill_name": skill_name,
                "versions": [
                    {
                        "version_id": version_id,
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "is_current": False,
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    return version_dir


def test_download_my_skill_returns_zip_file(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    """应下载我创建的技能 zip。"""
    _create_my_skill(
        test_app.state.marketplace.swe_root,
        "user-a",
        "src-a",
        "demo_skill",
    )
    test_app.state.marketplace.get_my_skills.return_value = [
        SimpleNamespace(skill_name="demo_skill", is_received=False),
    ]

    response = client.get(
        "/market/skills/mine/demo_skill/download",
        headers={
            "X-Source-Id": "src-a",
            "X-User-Id": "user-a",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="demo_skill.zip"'
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        assert sorted(zip_file.namelist()) == [
            "SKILL.md",
            "references/guide.md",
        ]


def test_download_my_skill_requires_x_user_id(
    client: TestClient,
) -> None:
    """缺少 X-User-Id 时应返回 400。"""
    response = client.get(
        "/market/skills/mine/demo_skill/download",
        headers={"X-Source-Id": "src-a"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "X-User-Id header is required"}


def test_download_my_skill_returns_404_when_skill_missing(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    """技能不存在时应返回 404。"""
    test_app.state.marketplace.get_my_skills.return_value = []

    response = client.get(
        "/market/skills/mine/demo_skill/download",
        headers={
            "X-Source-Id": "src-a",
            "X-User-Id": "user-a",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Skill not found"}


def test_download_market_skill_returns_current_version_zip(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    """应下载市场当前版本 zip。"""
    _create_market_skill(
        test_app.state.marketplace.marketplace_root,
        "src-a",
        "item-1",
    )
    test_app.state.marketplace.get_skill_detail.return_value = SimpleNamespace(
        name="demo_skill",
        version="1.2.3",
    )

    response = client.get(
        "/market/skills/item-1/download",
        headers={"X-Source-Id": "src-a"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="demo_skill-1.2.3.zip"'
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        assert sorted(zip_file.namelist()) == [
            "SKILL.md",
            "references/guide.md",
        ]


def test_download_market_skill_returns_404_when_invisible(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    """技能不可见时应返回 404。"""
    test_app.state.marketplace.get_skill_detail.return_value = None

    response = client.get(
        "/market/skills/item-1/download",
        headers={"X-Source-Id": "src-a"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Skill not found"}


def test_download_skill_version_returns_snapshot_zip(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """应下载指定历史版本快照，不回退到当前版本目录。"""
    _create_market_skill(
        test_app.state.marketplace.marketplace_root,
        "src-a",
        "item-1",
    )
    version_dir = _create_market_skill_version(
        test_app.state.marketplace.marketplace_root,
        "src-a",
        "item-1",
        "v1.0.0",
    )
    (version_dir / "SKILL.md").write_text(
        "# Snapshot Skill\n",
        encoding="utf-8",
    )

    def _fake_load_index(*_args, **_kwargs):
        return [SimpleNamespace(item_id="item-1")]

    monkeypatch.setattr(
        "market.app.routers.skill_versions.load_index",
        _fake_load_index,
    )

    response = client.get(
        "/market/skills/item-1/versions/v1.0.0/download",
        headers={"X-Source-Id": "src-a"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="demo_skill-v1.0.0.zip"'
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        assert (
            zip_file.read("SKILL.md").decode("utf-8") == "# Snapshot Skill\n"
        )


def test_download_skill_version_returns_404_when_version_missing(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """历史版本不存在时应返回 404。"""

    def _fake_load_index(*_args, **_kwargs):
        return [SimpleNamespace(item_id="item-1")]

    monkeypatch.setattr(
        "market.app.routers.skill_versions.load_index",
        _fake_load_index,
    )

    response = client.get(
        "/market/skills/item-1/versions/v9.9.9/download",
        headers={"X-Source-Id": "src-a"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Version v9.9.9 not found"}
