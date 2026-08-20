# -*- coding: utf-8 -*-
"""Expert Community marketplace service tests."""

from __future__ import annotations

from pathlib import Path
import json
import tomllib
from unittest.mock import AsyncMock, MagicMock

import pytest

from market.marketplace.fs import get_user_expert_dir, load_index
from market.marketplace.schemas import ExpertDistributionRequest
from market.marketplace.service import MarketplaceService


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a disconnected DB double."""
    db = MagicMock()
    db.is_connected = False
    db.fetch_one = AsyncMock(return_value=None)
    db.fetch_all = AsyncMock(return_value=[])
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_paths(tmp_path: Path) -> tuple[Path, Path]:
    """Create isolated market/runtime roots."""
    marketplace_root = tmp_path / ".swe.marketplace"
    swe_root = tmp_path / ".swe"
    marketplace_root.mkdir(parents=True, exist_ok=True)
    swe_root.mkdir(parents=True, exist_ok=True)
    return marketplace_root, swe_root


@pytest.fixture
def service(
    mock_db: MagicMock,
    mock_paths: tuple[Path, Path],
) -> MarketplaceService:
    """Create a MarketplaceService instance."""
    marketplace_root, swe_root = mock_paths
    return MarketplaceService(mock_db, marketplace_root, swe_root)


def _write_source_package(
    source_dir: Path,
    *,
    name: str = "Community Expert",
    description: str = "Expert description",
    creator_id: str = "author-a",
    creator_name: str = "Author A",
    category_id: int = 7,
    skill_content: str = "# skill a\n",
    mcp_config: str = '{"name": "mcp_a"}',
    scan_result: str = '{"status": "clean"}',
    declare_missing_skill: bool = False,
) -> None:
    """Write a synthetic expert source package."""
    (source_dir / "skills" / "skill_a").mkdir(parents=True, exist_ok=True)
    (source_dir / "mcp" / "mcp_a").mkdir(parents=True, exist_ok=True)

    skills_line = (
        'skills = ["missing_skill"]'
        if declare_missing_skill
        else 'skills = ["skill_a"]'
    )
    definition_toml = (
        f'name = "{name}"\n'
        f'description = "{description}"\n'
        f'creator_id = "{creator_id}"\n'
        f'creator_name = "{creator_name}"\n'
        f"category_id = {category_id}\n"
        'bbk_ids = ["100"]\n'
        f"{skills_line}\n"
        'mcps = ["mcp_a"]\n'
        "\n"
        "[model]\n"
        'provider = "openai"\n'
        'id = "gpt-4o-mini"\n'
    )

    (source_dir / "definition.toml").write_text(
        definition_toml,
        encoding="utf-8",
    )
    (source_dir / "skills" / "skill_a" / "SKILL.md").write_text(
        skill_content,
        encoding="utf-8",
    )
    (source_dir / "mcp" / "mcp_a" / "mcp.json").write_text(
        mcp_config,
        encoding="utf-8",
    )
    (source_dir / "scan_result.json").write_text(
        scan_result,
        encoding="utf-8",
    )


def _publish(
    service: MarketplaceService,
    source_id: str,
    source_dir: Path,
    *,
    overwrite: bool = True,
):
    return service.publish_expert(
        source_id,
        source_dir,
        operator_id="manager",
        operator_name="Manager",
        overwrite=overwrite,
    )


class TestPublishExpert:
    """Expert publication lifecycle tests."""

    @pytest.mark.asyncio
    async def test_publish_initial_version_creates_1_0_0(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir)

        item, version_unchanged = await _publish(
            service,
            "source-a",
            source_dir,
        )

        assert item.item_type == "expert"
        assert item.version == "1.0.0"
        assert version_unchanged is False

        snapshot_dir = (
            service.marketplace_root
            / "source-a"
            / "experts"
            / item.item_id
            / "versions"
            / "1.0.0"
        )
        assert (snapshot_dir / "definition.toml").is_file()
        assert (snapshot_dir / "skills" / "skill_a" / "SKILL.md").is_file()
        assert (snapshot_dir / "mcp" / "mcp_a" / "mcp.json").is_file()
        assert (snapshot_dir / "scan_result.json").is_file()

    @pytest.mark.asyncio
    async def test_publish_scans_each_bundled_skill_once(
        self,
        service: MarketplaceService,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir)
        scanned: list[Path] = []
        monkeypatch.setattr(
            "market.marketplace.service.scan_skill_directory",
            lambda path, **_kwargs: scanned.append(path),
        )

        await _publish(service, "source-a", source_dir)

        assert scanned == [source_dir / "skills" / "skill_a"]

    @pytest.mark.asyncio
    async def test_publish_replaces_stale_community_identity_and_scan_snapshot(
        self,
        service: MarketplaceService,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir)
        (source_dir / "definition.toml").write_text(
            (source_dir / "definition.toml").read_text(encoding="utf-8")
            + '\n[community]\nitem_id = "old-item"\nversion = "9.9.9"\ncontent_fingerprint = "old"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "market.marketplace.service.scan_skill_directory",
            lambda path, **_kwargs: MagicMock(
                to_dict=lambda: {"skill_name": path.name, "is_safe": True},
            ),
        )

        item, _ = await _publish(service, "source-a", source_dir)
        definition = (
            service.marketplace_root
            / "source-a"
            / "experts"
            / item.item_id
            / "definition.toml"
        ).read_text(encoding="utf-8")
        assert 'item_id = "old-item"' not in definition
        assert "[community]" not in definition
        scan_snapshot = json.loads(
            (
                service.marketplace_root
                / "source-a"
                / "experts"
                / item.item_id
                / "scan_result.json"
            ).read_text(encoding="utf-8"),
        )
        assert scan_snapshot["skills"][0]["skill_name"] == "skill_a"

    @pytest.mark.asyncio
    async def test_identical_republish_is_noop(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir)

        first_item, first_unchanged = await _publish(
            service,
            "source-a",
            source_dir,
        )
        second_item, second_unchanged = await _publish(
            service,
            "source-a",
            source_dir,
        )

        assert first_unchanged is False
        assert second_unchanged is True
        assert second_item.item_id == first_item.item_id
        assert second_item.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_changed_content_bumps_patch_version(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir)

        first_item, _ = await _publish(service, "source-a", source_dir)

        (source_dir / "skills" / "skill_a" / "SKILL.md").write_text(
            "# skill a updated\n",
            encoding="utf-8",
        )
        second_item, second_unchanged = await _publish(
            service,
            "source-a",
            source_dir,
        )

        assert second_unchanged is False
        assert second_item.item_id == first_item.item_id
        assert second_item.version == "1.0.1"

    @pytest.mark.asyncio
    async def test_missing_declared_dependency_blocks_publish(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir, declare_missing_skill=True)
        (source_dir / "skills" / "skill_a" / "SKILL.md").unlink()

        with pytest.raises(ValueError, match="dependency"):
            await _publish(service, "source-a", source_dir)

    @pytest.mark.asyncio
    async def test_same_name_without_overwrite_conflicts(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir, name="Shared Expert")

        await _publish(service, "source-a", source_dir)

        with pytest.raises(ValueError, match="already exists"):
            await _publish(service, "source-a", source_dir, overwrite=False)

    @pytest.mark.asyncio
    async def test_restore_and_unpublish_keep_history(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir)

        item, _ = await _publish(service, "source-a", source_dir)
        (source_dir / "skills" / "skill_a" / "SKILL.md").write_text(
            "# skill a updated\n",
            encoding="utf-8",
        )
        updated_item, _ = await _publish(service, "source-a", source_dir)

        restored = await service.restore_expert_version(
            "source-a",
            item.item_id,
            "1.0.0",
            operator_id="manager",
            operator_name="Manager",
        )
        unpublished = await service.unpublish_expert(
            "source-a",
            item.item_id,
            operator_id="manager",
            operator_name="Manager",
        )

        assert updated_item.version == "1.0.1"
        assert restored.version == "1.0.0"
        assert unpublished is True

        items = load_index(service.marketplace_root, "source-a")
        saved = next(
            saved_item
            for saved_item in items
            if saved_item.item_id == item.item_id
        )
        assert saved.status == "inactive"
        versions_root = (
            service.marketplace_root
            / "source-a"
            / "experts"
            / item.item_id
            / "versions"
        )
        assert (versions_root / "1.0.0").is_dir()
        assert (versions_root / "1.0.1").is_dir()


class TestReceivedExpertLifecycle:
    """Community installation keeps dependencies private and frozen."""

    @pytest.mark.asyncio
    async def test_install_copies_private_dependencies_and_community_identity(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir)
        item, _ = await _publish(service, "source-a", source_dir)

        installed = await service.install_expert(
            "source-a",
            item.item_id,
            "alice",
            "research",
        )

        assert installed.success is True
        expert_dir = get_user_expert_dir(
            service.swe_root,
            "alice",
            "research",
            "source-a",
        )
        definition = expert_dir / f"{installed.definition_id}.toml"
        dependency_dir = expert_dir / f"{installed.definition_id}.dependencies"
        assert definition.is_file()
        assert (dependency_dir / "skills" / "skill_a" / "SKILL.md").is_file()
        assert (dependency_dir / "mcp" / "mcp_a" / "mcp.json").is_file()
        mcp_snapshot = json.loads(
            (dependency_dir / "mcp" / "config.json").read_text(
                encoding="utf-8",
            ),
        )
        assert mcp_snapshot == {"mcp_a": {"name": "mcp_a"}}
        payload = tomllib.loads(definition.read_text(encoding="utf-8"))
        assert payload["enabled"] is True
        assert payload["community"]["item_id"] == item.item_id
        assert payload["community"]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_install_normalizes_bundled_mcp_server_config(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(
            source_dir,
            mcp_config=(
                '{"mcpServers":{"mcp_a":{"command":"tool",'
                '"env":{"TOKEN":"value"},"headers":{"X-Test":"yes"}}}}'
            ),
        )
        item, _ = await _publish(service, "source-a", source_dir)

        installed = await service.install_expert(
            "source-a",
            item.item_id,
            "alice",
        )

        config = json.loads(
            (
                get_user_expert_dir(
                    service.swe_root,
                    "alice",
                    "default",
                    "source-a",
                )
                / f"{installed.definition_id}.dependencies"
                / "mcp"
                / "config.json"
            ).read_text(encoding="utf-8"),
        )
        assert config["mcp_a"]["env"] == {"TOKEN": "value"}
        assert config["mcp_a"]["headers"] == {"X-Test": "yes"}
        assert config["mcp_a"]["transport"] == "stdio"

    @pytest.mark.asyncio
    async def test_install_does_not_overwrite_existing_received_expert(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir)
        item, _ = await _publish(service, "source-a", source_dir)
        installed = await service.install_expert(
            "source-a",
            item.item_id,
            "alice",
        )
        expert_dir = get_user_expert_dir(
            service.swe_root,
            "alice",
            "default",
            "source-a",
        )
        definition = expert_dir / f"{installed.definition_id}.toml"
        definition.write_text(
            definition.read_text(encoding="utf-8").replace(
                "Expert description",
                "Local variant",
            ),
            encoding="utf-8",
        )

        second = await service.install_expert(
            "source-a",
            item.item_id,
            "alice",
        )

        assert second.success is False
        assert "already installed" in (second.reason or "")
        assert "Local variant" in definition.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_distribution_silently_overwrites_local_variant_and_preserves_enablement(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir, skill_content="# original\n")
        item, _ = await _publish(service, "source-a", source_dir)
        installed = await service.install_expert(
            "source-a",
            item.item_id,
            "alice",
        )
        expert_dir = get_user_expert_dir(
            service.swe_root,
            "alice",
            "default",
            "source-a",
        )
        definition = expert_dir / f"{installed.definition_id}.toml"
        definition.write_text(
            definition.read_text(encoding="utf-8")
            .replace("enabled = true", "enabled = false")
            .replace("Expert description", "Local variant"),
            encoding="utf-8",
        )
        (source_dir / "skills" / "skill_a" / "SKILL.md").write_text(
            "# updated\n",
            encoding="utf-8",
        )
        updated, _ = await _publish(service, "source-a", source_dir)

        result = await service.distribute_expert(
            "source-a",
            item.item_id,
            "manager",
            ExpertDistributionRequest(
                target_type="user_id",
                target_values=["alice"],
            ),
        )

        assert result.distributed_count == 1
        payload = tomllib.loads(definition.read_text(encoding="utf-8"))
        assert payload["enabled"] is False
        assert payload["description"] == "Expert description"
        assert payload["community"]["version"] == updated.version
        assert (
            expert_dir
            / f"{installed.definition_id}.dependencies"
            / "skills"
            / "skill_a"
            / "SKILL.md"
        ).read_text(encoding="utf-8") == "# updated\n"

    @pytest.mark.asyncio
    async def test_recall_removes_received_definition_by_community_item_id(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir)
        item, _ = await _publish(service, "source-a", source_dir)
        installed = await service.install_expert(
            "source-a",
            item.item_id,
            "alice",
        )

        recalled = await service.recall_expert(
            "source-a",
            item.item_id,
            "manager",
            ["alice"],
        )

        expert_dir = get_user_expert_dir(
            service.swe_root,
            "alice",
            "default",
            "source-a",
        )
        assert recalled.recalled_count == 1
        assert not (expert_dir / f"{installed.definition_id}.toml").exists()
        assert not (
            expert_dir / f"{installed.definition_id}.dependencies"
        ).exists()

    @pytest.mark.asyncio
    async def test_distribution_installs_first_copy_to_default_profile(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir)
        item, _ = await _publish(service, "source-a", source_dir)

        distributed = await service.distribute_expert(
            "source-a",
            item.item_id,
            "manager",
            ExpertDistributionRequest(
                target_type="user_id",
                target_values=["alice"],
            ),
        )

        assert distributed.distributed_count == 1
        assert distributed.results[0].definition_id
        expert_dir = get_user_expert_dir(
            service.swe_root,
            "alice",
            "default",
            "source-a",
        )
        assert (
            expert_dir / f"{distributed.results[0].definition_id}.toml"
        ).is_file()

    @pytest.mark.asyncio
    async def test_recall_removes_received_copies_from_every_profile(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir)
        item, _ = await _publish(service, "source-a", source_dir)
        default_install = await service.install_expert(
            "source-a",
            item.item_id,
            "alice",
        )
        research_install = await service.install_expert(
            "source-a",
            item.item_id,
            "alice",
            "research",
        )

        recalled = await service.recall_expert(
            "source-a",
            item.item_id,
            "manager",
            ["alice"],
        )

        assert recalled.recalled_count == 1
        for agent_id, definition_id in (
            ("default", default_install.definition_id),
            ("research", research_install.definition_id),
        ):
            expert_dir = get_user_expert_dir(
                service.swe_root,
                "alice",
                agent_id,
                "source-a",
            )
            assert not (expert_dir / f"{definition_id}.toml").exists()
            assert not (expert_dir / f"{definition_id}.dependencies").exists()

    @pytest.mark.asyncio
    async def test_all_user_recall_falls_back_to_local_received_scopes(
        self,
        service: MarketplaceService,
        tmp_path: Path,
    ) -> None:
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        _write_source_package(source_dir)
        item, _ = await _publish(service, "source-a", source_dir)
        installed = await service.install_expert(
            "source-a",
            item.item_id,
            "alice",
        )

        recalled = await service.recall_expert(
            "source-a",
            item.item_id,
            "manager",
        )

        expert_dir = get_user_expert_dir(
            service.swe_root,
            "alice",
            "default",
            "source-a",
        )
        assert recalled.recalled_count == 1
        assert not (expert_dir / f"{installed.definition_id}.toml").exists()
