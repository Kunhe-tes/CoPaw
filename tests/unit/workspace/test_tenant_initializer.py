# -*- coding: utf-8 -*-
"""Unit tests for TenantInitializer.

Tests tenant directory initialization, idempotency, and runtime integration.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import pytest

from swe.app.workspace.tenant_initializer import TenantInitializer
from swe.app.workspace.tenant_pool import TenantWorkspacePool
from swe.config.config import (
    Config,
    AgentsConfig,
    AgentProfileRef,
    ChannelConfig,
    ConsoleConfig,
    SecurityConfig,
    ToolGuardConfig,
    ToolsConfig,
    ZhaohuConfig,
)
from swe.config.utils import save_config
from swe.constant import BUILTIN_QA_AGENT_ID


def _build_source_template(
    tmp_path,
    *,
    source_id="rmassist",
    tpl_zhaohu=None,
    config_zhaohu=None,
    agent_has_zhaohu=True,
):
    """Build a source template directory (default_{source_id}) for tests."""
    template_dir = tmp_path / f"default_{source_id}"
    template_ws = template_dir / "workspaces" / "default"
    template_ws.mkdir(parents=True)

    channels = ChannelConfig(
        console=ConsoleConfig(media_dir="/tmp/console-media"),
    )
    if config_zhaohu is not None:
        channels.zhaohu = ZhaohuConfig(**config_zhaohu)
    tpl_config = Config(
        agents=AgentsConfig(
            active_agent="default",
            profiles={
                "default": AgentProfileRef(
                    id="default",
                    workspace_dir=str(template_ws),
                ),
            },
        ),
        channels=channels,
        tools=ToolsConfig(),
        security=SecurityConfig(tool_guard=ToolGuardConfig(enabled=False)),
    )
    save_config(tpl_config, template_dir / "config.json")

    agent_payload = {
        "id": "default",
        "name": "Default Template Agent",
        "workspace_dir": str(template_ws),
    }
    if agent_has_zhaohu:
        agent_payload["channels"] = {"zhaohu": tpl_zhaohu or {}}
    (template_ws / "agent.json").write_text(
        json.dumps(agent_payload),
        encoding="utf-8",
    )
    for filename, content in {
        "AGENTS.md": "# agents template\n",
        "BOOTSTRAP.md": "# bootstrap template\n",
        "HEARTBEAT.md": "# heartbeat template\n",
        "MEMORY.md": "# memory template\n",
        "PROFILE.md": "# profile template\n",
        "SOUL.md": "# soul template\n",
    }.items():
        (template_ws / filename).write_text(content, encoding="utf-8")
    (template_ws / "jobs.json").write_text("{}", encoding="utf-8")
    return template_dir


class TestTenantInitializerBasics:
    """Basic TenantInitializer functionality tests."""

    def test_tenant_initializer_creates_expected_structure(self, tmp_path):
        """TenantInitializer creates tenant directory with workspaces and skill_pool."""
        initializer = TenantInitializer(tmp_path, "tenant-acme")
        initializer.initialize()

        tenant_dir = tmp_path / "tenant-acme"
        assert tenant_dir.is_dir()
        assert (tenant_dir / "workspaces" / "default").is_dir()
        assert (tenant_dir / "workspaces" / BUILTIN_QA_AGENT_ID).is_dir()
        assert (tenant_dir / "skill_pool").is_dir()

    def test_tenant_initializer_is_idempotent(self, tmp_path):
        """TenantInitializer can be called multiple times without errors."""
        initializer = TenantInitializer(tmp_path, "tenant-acme")

        initializer.initialize()
        initializer.initialize()

        tenant_dir = tmp_path / "tenant-acme"
        assert (tenant_dir / "workspaces" / "default" / "jobs.json").exists()


class TestEnsureSeededBootstrap:
    """Tests for ensure_seeded_bootstrap - runtime-safe skill seeding."""

    def test_ensure_seeded_bootstrap_seeds_config_and_workspace_template(
        self,
        tmp_path,
    ):
        """New tenants inherit template config and workspace scaffold."""
        default_tenant = tmp_path / "default"
        default_workspace = default_tenant / "workspaces" / "default"
        default_workspace.mkdir(parents=True)

        default_config = Config(
            agents=AgentsConfig(
                active_agent="default",
                profiles={
                    "default": AgentProfileRef(
                        id="default",
                        workspace_dir=str(default_workspace),
                    ),
                },
                language="en",
            ),
            channels=ChannelConfig(
                console=ConsoleConfig(media_dir="/tmp/console-media"),
            ),
            tools=ToolsConfig(),
            security=SecurityConfig(
                tool_guard=ToolGuardConfig(enabled=False),
            ),
        )
        save_config(default_config, default_tenant / "config.json")

        agent_payload = {
            "id": "default",
            "name": "Default Template Agent",
            "description": "template description",
            "workspace_dir": str(default_workspace),
            "language": "en",
        }
        (default_workspace / "agent.json").write_text(
            json.dumps(agent_payload),
            encoding="utf-8",
        )

        for filename, content in {
            "AGENTS.md": "# agents template\n",
            "BOOTSTRAP.md": "# bootstrap template\n",
            "HEARTBEAT.md": "# heartbeat template\n",
            "MEMORY.md": "# memory template\n",
            "PROFILE.md": "# profile template\n",
            "SOUL.md": "# soul template\n",
        }.items():
            (default_workspace / filename).write_text(
                content,
                encoding="utf-8",
            )

        (default_workspace / "sessions").mkdir()
        (default_workspace / "sessions" / "old.json").write_text(
            "{}",
            encoding="utf-8",
        )
        (default_workspace / "memory").mkdir()
        (default_workspace / "memory" / "old.md").write_text(
            "keep out",
            encoding="utf-8",
        )
        (default_workspace / "jobs.json").write_text(
            json.dumps({"version": 1, "jobs": [{"id": "job-1"}]}),
            encoding="utf-8",
        )
        (default_workspace / "chats.json").write_text(
            json.dumps({"version": 1, "chats": [{"id": "chat-1"}]}),
            encoding="utf-8",
        )
        (default_workspace / "token_usage.json").write_text(
            '[{"prompt_tokens": 1}]',
            encoding="utf-8",
        )

        new_init = TenantInitializer(tmp_path, "tenant-bootstrap")
        new_init.ensure_seeded_bootstrap()

        tenant_dir = tmp_path / "tenant-bootstrap"
        workspace_dir = tenant_dir / "workspaces" / "default"

        config_data = json.loads(
            (tenant_dir / "config.json").read_text(encoding="utf-8"),
        )
        assert config_data["agents"]["active_agent"] == "default"
        assert config_data["agents"]["profiles"]["default"][
            "workspace_dir"
        ] == str(workspace_dir)

        agent_data = json.loads(
            (workspace_dir / "agent.json").read_text(encoding="utf-8"),
        )
        assert agent_data["name"] == "Default Template Agent"
        assert agent_data["workspace_dir"] == str(workspace_dir)

        for filename in (
            "AGENTS.md",
            "BOOTSTRAP.md",
            "HEARTBEAT.md",
            "MEMORY.md",
            "PROFILE.md",
            "SOUL.md",
        ):
            assert (workspace_dir / filename).exists()

        assert (workspace_dir / "sessions").is_dir()
        assert (workspace_dir / "memory").is_dir()
        assert not (workspace_dir / "sessions" / "old.json").exists()
        assert not (workspace_dir / "memory" / "old.md").exists()

        jobs_data = json.loads(
            (workspace_dir / "jobs.json").read_text(encoding="utf-8"),
        )
        chats_data = json.loads(
            (workspace_dir / "chats.json").read_text(encoding="utf-8"),
        )
        token_usage_data = json.loads(
            (workspace_dir / "token_usage.json").read_text(encoding="utf-8"),
        )
        assert jobs_data == {"version": 1, "jobs": []}
        assert chats_data == {"version": 1, "chats": []}
        assert token_usage_data == {}

    def test_ensure_seeded_bootstrap_seeds_pool_but_ignores_unregistered_workspace(
        self,
        tmp_path,
    ):
        """Runtime bootstrap seeds Pool entries but ignores unmanaged content."""
        from swe.agents.skills_manager import (
            get_skill_pool_dir,
            get_pool_skill_manifest_path,
            get_workspace_skills_dir,
            _write_json_atomic,
        )

        # Setup default tenant with skills
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        # Create default pool skill
        default_pool = get_skill_pool_dir(working_dir=default_init.tenant_dir)
        default_pool.mkdir(parents=True, exist_ok=True)

        pool_skill = default_pool / "pool-skill"
        pool_skill.mkdir()
        (pool_skill / "SKILL.md").write_text(
            "---\nname: pool-skill\ndescription: Pool Skill\n---\n",
            encoding="utf-8",
        )

        manifest_path = get_pool_skill_manifest_path(
            working_dir=default_init.tenant_dir,
        )
        _write_json_atomic(
            manifest_path,
            {"skills": {"pool-skill": {"name": "pool-skill"}}},
        )

        # Create default workspace skill
        default_workspace = default_init.tenant_dir / "workspaces" / "default"
        default_skills = get_workspace_skills_dir(default_workspace)
        default_skills.mkdir(parents=True, exist_ok=True)

        ws_skill = default_skills / "ws-skill"
        ws_skill.mkdir()
        (ws_skill / "SKILL.md").write_text(
            "---\nname: ws-skill\ndescription: WS Skill\n---\n",
            encoding="utf-8",
        )

        # Run ensure_seeded_bootstrap (runtime bootstrap path)
        new_init = TenantInitializer(tmp_path, "new-tenant")
        result = new_init.ensure_seeded_bootstrap()

        # Verify minimal bootstrap completed
        assert result["minimal"] is True

        # Verify skills were seeded
        assert result["pool_seed"]["seeded"] is True
        assert result["pool_seed"]["source"] == "default"
        assert "pool-skill" in result["pool_seed"]["skills"]

        assert result["workspace_seed"]["seeded"] is False
        assert result["workspace_seed"]["skills"] == []
        new_default_workspace = new_init.tenant_dir / "workspaces" / "default"
        assert not (
            get_workspace_skills_dir(new_default_workspace) / "ws-skill"
        ).exists()

        # Verify QA agent was NOT created (runtime bootstrap boundary)
        assert not (
            new_init.tenant_dir / "workspaces" / BUILTIN_QA_AGENT_ID
        ).exists()

    def test_has_seeded_bootstrap_does_not_require_bootstrap_md(
        self,
        tmp_path,
    ):
        """Deleting BOOTSTRAP.md should not mark scaffold incomplete."""
        default_tenant = tmp_path / "default"
        default_workspace = default_tenant / "workspaces" / "default"
        default_workspace.mkdir(parents=True)

        save_config(
            Config(
                agents=AgentsConfig(
                    active_agent="default",
                    profiles={
                        "default": AgentProfileRef(
                            id="default",
                            workspace_dir=str(default_workspace),
                        ),
                    },
                ),
            ),
            default_tenant / "config.json",
        )
        (default_workspace / "agent.json").write_text(
            json.dumps(
                {
                    "id": "default",
                    "name": "Default Template Agent",
                    "workspace_dir": str(default_workspace),
                },
            ),
            encoding="utf-8",
        )
        for filename in (
            "AGENTS.md",
            "BOOTSTRAP.md",
            "HEARTBEAT.md",
            "MEMORY.md",
            "PROFILE.md",
            "SOUL.md",
        ):
            (default_workspace / filename).write_text(
                "# template\n",
                encoding="utf-8",
            )

        initializer = TenantInitializer(tmp_path, "tenant-bootstrap")
        initializer.ensure_seeded_bootstrap()

        tenant_bootstrap = (
            tmp_path
            / "tenant-bootstrap"
            / "workspaces"
            / "default"
            / "BOOTSTRAP.md"
        )
        tenant_bootstrap.unlink()

        assert initializer.has_seeded_bootstrap() is True

    def test_ensure_seeded_bootstrap_can_skip_bootstrap_md(
        self,
        tmp_path,
    ):
        """Runtime bootstrap can suppress the first-chat bootstrap file."""
        default_tenant = tmp_path / "default"
        default_workspace = default_tenant / "workspaces" / "default"
        default_workspace.mkdir(parents=True)

        save_config(
            Config(
                agents=AgentsConfig(
                    active_agent="default",
                    profiles={
                        "default": AgentProfileRef(
                            id="default",
                            workspace_dir=str(default_workspace),
                        ),
                    },
                    language="en",
                ),
            ),
            default_tenant / "config.json",
        )
        (default_workspace / "agent.json").write_text(
            json.dumps(
                {
                    "id": "default",
                    "name": "Default Template Agent",
                    "workspace_dir": str(default_workspace),
                    "language": "en",
                },
            ),
            encoding="utf-8",
        )
        for filename in (
            "AGENTS.md",
            "BOOTSTRAP.md",
            "HEARTBEAT.md",
            "MEMORY.md",
            "PROFILE.md",
            "SOUL.md",
        ):
            (default_workspace / filename).write_text(
                "# template\n",
                encoding="utf-8",
            )

        initializer = TenantInitializer(tmp_path, "tenant-no-bootstrap")
        initializer.ensure_seeded_bootstrap(enable_bootstrap_chat=False)

        workspace_dir = (
            tmp_path / "tenant-no-bootstrap" / "workspaces" / "default"
        )
        assert not (workspace_dir / "BOOTSTRAP.md").exists()
        for filename in (
            "AGENTS.md",
            "HEARTBEAT.md",
            "MEMORY.md",
            "PROFILE.md",
            "SOUL.md",
        ):
            assert (workspace_dir / filename).exists()

    def test_ensure_seeded_bootstrap_is_idempotent(self, tmp_path):
        """Runtime bootstrap is idempotent - second call does not re-seed."""
        from swe.agents.skills_manager import (
            get_skill_pool_dir,
            get_pool_skill_manifest_path,
            _write_json_atomic,
        )

        # Setup default tenant
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        default_pool = get_skill_pool_dir(working_dir=default_init.tenant_dir)
        default_pool.mkdir(parents=True, exist_ok=True)

        skill_dir = default_pool / "default-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: default-skill\ndescription: Default\n---\n",
            encoding="utf-8",
        )

        manifest_path = get_pool_skill_manifest_path(
            working_dir=default_init.tenant_dir,
        )
        _write_json_atomic(
            manifest_path,
            {"skills": {"default-skill": {"name": "default-skill"}}},
        )

        # First bootstrap
        new_init = TenantInitializer(tmp_path, "new-tenant")
        result1 = new_init.ensure_seeded_bootstrap()
        assert result1["pool_seed"]["seeded"] is True

        # Second bootstrap should be skipped
        result2 = new_init.ensure_seeded_bootstrap()
        assert result2["pool_seed"]["seeded"] is False
        assert result2["pool_seed"]["source"] is None

    def test_ensure_seeded_bootstrap_falls_back_to_builtin(self, tmp_path):
        """Runtime bootstrap falls back to builtin when no default template."""
        # Create default tenant without skills
        default_init = TenantInitializer(tmp_path, "default")
        default_init.ensure_directory_structure()

        # Run ensure_seeded_bootstrap for new tenant
        new_init = TenantInitializer(tmp_path, "new-tenant")
        result = new_init.ensure_seeded_bootstrap()

        assert result["minimal"] is True
        # Should fall back to builtin
        assert result["pool_seed"]["seeded"] is True
        assert result["pool_seed"]["source"] == "builtin"
        assert len(result["pool_seed"]["skills"]) > 0

    def test_new_tenant_inherits_full_zhaohu_from_template(self, tmp_path):
        """New tenant inherits non-empty zhaohu config from source template."""
        _build_source_template(
            tmp_path,
            tpl_zhaohu={
                "push_url": "https://tpl/push",
                "sys_id": "RMS",
                "robot_open_id": "ROBOT_TPL",
                "channel": "ZH",
                "net": "DMZ",
                "oauth_url": "https://tpl/oauth",
                "client_id": "CID_TPL",
                "client_secret": "SECRET_TPL",
            },
        )

        new_init = TenantInitializer(
            tmp_path,
            "tenant-bootstrap",
            source_id="rmassist",
        )
        new_init.ensure_seeded_bootstrap()

        agent_data = json.loads(
            (
                new_init.tenant_dir / "workspaces" / "default" / "agent.json"
            ).read_text(encoding="utf-8"),
        )
        zhaohu = agent_data["channels"]["zhaohu"]
        assert zhaohu["push_url"] == "https://tpl/push"
        assert zhaohu["sys_id"] == "RMS"
        assert zhaohu["robot_open_id"] == "ROBOT_TPL"
        assert zhaohu["channel"] == "ZH"
        assert zhaohu["net"] == "DMZ"
        assert zhaohu["oauth_url"] == "https://tpl/oauth"
        assert zhaohu["client_id"] == "CID_TPL"
        assert zhaohu["client_secret"] == "SECRET_TPL"

    def test_template_zhaohu_empty_fields_fall_back_to_config(self, tmp_path):
        """Empty template zhaohu fields keep config.json / env defaults."""
        _build_source_template(
            tmp_path,
            tpl_zhaohu={"push_url": "", "robot_open_id": "ROBOT_TPL"},
            config_zhaohu={
                "push_url": "https://cfg/push",
                "client_id": "CID_CFG",
            },
        )

        new_init = TenantInitializer(
            tmp_path,
            "tenant-bootstrap",
            source_id="rmassist",
        )
        new_init.ensure_seeded_bootstrap()

        agent_data = json.loads(
            (
                new_init.tenant_dir / "workspaces" / "default" / "agent.json"
            ).read_text(encoding="utf-8"),
        )
        zhaohu = agent_data["channels"]["zhaohu"]
        assert zhaohu["push_url"] == "https://cfg/push"
        assert zhaohu["client_id"] == "CID_CFG"
        assert zhaohu["robot_open_id"] == "ROBOT_TPL"

    def test_template_without_zhaohu_keeps_existing_behavior(self, tmp_path):
        """Template without zhaohu node keeps prior behavior (config.json values)."""
        _build_source_template(
            tmp_path,
            agent_has_zhaohu=False,
            config_zhaohu={
                "push_url": "https://cfg/push",
                "client_id": "CID_CFG",
            },
        )

        new_init = TenantInitializer(
            tmp_path,
            "tenant-bootstrap",
            source_id="rmassist",
        )
        new_init.ensure_seeded_bootstrap()

        agent_data = json.loads(
            (
                new_init.tenant_dir / "workspaces" / "default" / "agent.json"
            ).read_text(encoding="utf-8"),
        )
        zhaohu = agent_data["channels"]["zhaohu"]
        assert zhaohu["push_url"] == "https://cfg/push"
        assert zhaohu["client_id"] == "CID_CFG"

    def test_idempotent_scaffold_does_not_override_inherited_zhaohu(
        self,
        tmp_path,
    ):
        """Re-running bootstrap must not override the inherited zhaohu snapshot."""
        _build_source_template(
            tmp_path,
            tpl_zhaohu={
                "push_url": "https://tpl/push",
                "robot_open_id": "ROBOT_TPL",
            },
        )

        new_init = TenantInitializer(
            tmp_path,
            "tenant-bootstrap",
            source_id="rmassist",
        )
        new_init.ensure_seeded_bootstrap()
        agent_path = (
            new_init.tenant_dir / "workspaces" / "default" / "agent.json"
        )
        first = json.loads(agent_path.read_text(encoding="utf-8"))

        # Simulate template change after the new tenant was created
        tpl_agent_path = (
            tmp_path
            / "default_rmassist"
            / "workspaces"
            / "default"
            / "agent.json"
        )
        tpl = json.loads(tpl_agent_path.read_text(encoding="utf-8"))
        tpl["channels"]["zhaohu"]["push_url"] = "https://tpl/changed"
        tpl_agent_path.write_text(json.dumps(tpl), encoding="utf-8")

        new_init.ensure_seeded_bootstrap()
        second = json.loads(agent_path.read_text(encoding="utf-8"))
        assert second["channels"]["zhaohu"] == first["channels"]["zhaohu"]


class TestTenantPoolIntegration:
    """Runtime integration tests for TenantWorkspacePool."""

    @pytest.mark.asyncio
    async def test_tenant_pool_get_or_create_initializes_tenant_dir(
        self,
        tmp_path,
    ):
        """TenantWorkspacePool.get_or_create initializes tenant directory structure."""
        pool = TenantWorkspacePool(tmp_path)

        workspace = await pool.get_or_create("tenant-runtime")

        assert workspace is not None
        assert (
            tmp_path / "tenant-runtime" / "workspaces" / "default"
        ).is_dir()
