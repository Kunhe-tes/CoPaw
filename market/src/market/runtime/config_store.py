# -*- coding: utf-8 -*-
"""market 内部使用的最小 MCP 配置模型与持久化读写。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .context import canonicalize_scope_id, migrate_legacy_scope_dir_if_needed


class AgentProfileRef(BaseModel):
    """root config 中记录的 agent 引用。"""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Agent ID")
    workspace_dir: str = Field(..., description="Agent 工作区目录")
    enabled: bool = Field(default=True, description="是否启用")


class RootAgentsSection(BaseModel):
    """root config 的 agents 段。"""

    model_config = ConfigDict(extra="ignore")

    active_agent: str = Field(default="default", description="当前激活 agent")
    profiles: Dict[str, AgentProfileRef] = Field(
        default_factory=dict,
        description="Agent 引用表",
    )


class AgentsRootConfig(BaseModel):
    """market 读写 tenant 根配置时使用的最小模型。"""

    model_config = ConfigDict(extra="allow")

    agents: RootAgentsSection = Field(default_factory=RootAgentsSection)


class MCPClientConfig(BaseModel):
    """单个 MCP 客户端配置。"""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str = Field(default="", description="客户端名称，默认取 client_key")
    description: str = ""
    enabled: bool = True
    transport: Literal["stdio", "streamable_http", "sse"] = "stdio"
    url: str = ""
    headers: Dict[str, str] = Field(default_factory=dict)
    command: str = ""
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    cwd: str = ""
    source: str = Field(default="", description="来源标识")
    market_client_key: str = Field(
        default="",
        description="市场来源 client_key",
    )
    distributed_by: str = Field(default="", description="分发者 user_id")
    lazy_load: bool = Field(default=False, description="是否懒加载")
    created_at: str = Field(default="", description="创建时间")
    updated_at: str = Field(default="", description="更新时间")
    version: str = Field(default="1.0.0", description="MCP 版本号")
    received_version: str = Field(
        default="",
        description="市场分发时接收的版本号",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, data):
        """兼容第三方常见字段别名与老配置。"""
        if not isinstance(data, dict):
            return data

        payload = dict(data)

        if "isActive" in payload and "enabled" not in payload:
            payload["enabled"] = payload["isActive"]
        if "baseUrl" in payload and "url" not in payload:
            payload["url"] = payload["baseUrl"]
        if "type" in payload and "transport" not in payload:
            payload["transport"] = payload["type"]
        if (
            "transport" not in payload
            and (payload.get("url") or payload.get("baseUrl"))
            and not payload.get("command")
        ):
            payload["transport"] = "streamable_http"

        raw_transport = payload.get("transport")
        if isinstance(raw_transport, str):
            normalized = raw_transport.strip().lower()
            alias_map = {
                "streamablehttp": "streamable_http",
                "streamable-http": "streamable_http",
                "http": "streamable_http",
                "stdio": "stdio",
                "sse": "sse",
            }
            payload["transport"] = alias_map.get(normalized, normalized)

        return payload

    @model_validator(mode="after")
    def validate_transport_config(self):
        """按 transport 校验必填字段。"""
        if self.transport == "stdio":
            if not self.command.strip():
                raise ValueError("stdio MCP client requires non-empty command")
            return self

        if not self.url.strip():
            raise ValueError(
                f"{self.transport} MCP client requires non-empty url",
            )
        return self


class MCPConfig(BaseModel):
    """Agent 下的 MCP clients 配置。"""

    model_config = ConfigDict(extra="allow")

    clients: Dict[str, MCPClientConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def fill_client_names(cls, data):
        """自动填充每个 client 的 name 字段（使用 client_key）。"""
        if not isinstance(data, dict):
            return data

        clients = data.get("clients", {})
        if isinstance(clients, dict):
            for client_key, client_config in clients.items():
                if isinstance(client_config, dict):
                    # 如果没有 name 字段，用 client_key 填充
                    if (
                        "name" not in client_config
                        or not client_config["name"]
                    ):
                        client_config["name"] = client_key
        return data


class AgentProfileConfig(BaseModel):
    """workspace/agent.json 的最小读写模型。"""

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent 名称")
    description: str = Field(default="", description="Agent 描述")
    workspace_dir: str = Field(default="", description="工作区目录")
    mcp: MCPConfig | None = Field(default=None, description="MCP 配置")


def _normalize_workspace_bound_paths(data: object) -> object:
    """把残留的 legacy scope workspace 路径收敛成 canonical 目录。"""
    if not isinstance(data, dict):
        return data

    legacy_scope_prefix = "scope.v1."

    def _rewrite(value: object) -> object:
        if not isinstance(value, str) or not value:
            return value

        path = Path(value).expanduser()
        normalized_parts: list[str] = []
        changed = False
        for part in path.parts:
            if not part.startswith(legacy_scope_prefix):
                normalized_parts.append(part)
                continue

            try:
                normalized_parts.append(canonicalize_scope_id(part))
            except ValueError:
                normalized_parts.append(part[len(legacy_scope_prefix) :])
            else:
                changed = True
                continue

            changed = True

        if changed:
            return str(Path(*normalized_parts))
        return str(path)

    def _walk(obj: object, key: str | None = None) -> object:
        if isinstance(obj, dict):
            return {k: _walk(v, str(k)) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(item, key) for item in obj]
        if key == "workspace_dir":
            return _rewrite(obj)
        return obj

    return _walk(data)


def get_tenant_working_dir(swe_root: Path, tenant_id: str) -> Path:
    """获取 tenant 根目录。"""
    return migrate_legacy_scope_dir_if_needed(
        Path(swe_root).expanduser(),
        tenant_id,
    )


def get_tenant_config_path(swe_root: Path, tenant_id: str) -> Path:
    """获取 tenant 的 config.json 路径。"""
    return get_tenant_working_dir(swe_root, tenant_id) / "config.json"


def _default_workspace_dir(swe_root: Path, tenant_id: str) -> Path:
    """构造 default agent 的默认工作区路径。"""
    return (
        get_tenant_working_dir(swe_root, tenant_id) / "workspaces" / "default"
    )


def _build_default_root_config(
    swe_root: Path,
    tenant_id: str,
) -> AgentsRootConfig:
    """在 config.json 缺失时构造一个最小默认配置。"""
    workspace_dir = _default_workspace_dir(swe_root, tenant_id)
    return AgentsRootConfig(
        agents=RootAgentsSection(
            active_agent="default",
            profiles={
                "default": AgentProfileRef(
                    id="default",
                    workspace_dir=str(workspace_dir),
                ),
            },
        ),
    )


def load_root_config(swe_root: Path, tenant_id: str) -> AgentsRootConfig:
    """读取 tenant 根配置；缺失时返回最小默认值。"""
    config_path = get_tenant_config_path(swe_root, tenant_id)
    if not config_path.is_file():
        return _build_default_root_config(swe_root, tenant_id)

    with open(config_path, "r", encoding="utf-8") as file:
        data = _normalize_workspace_bound_paths(json.load(file))

    config = AgentsRootConfig.model_validate(data)
    if not config.agents.profiles:
        return _build_default_root_config(swe_root, tenant_id)
    return config


def save_root_config(
    swe_root: Path,
    tenant_id: str,
    config: AgentsRootConfig,
) -> None:
    """保存 tenant 根配置。"""
    config_path = get_tenant_config_path(swe_root, tenant_id)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as file:
        json.dump(
            config.model_dump(mode="json", exclude_none=True),
            file,
            ensure_ascii=False,
            indent=2,
        )


def load_agent_config(
    swe_root: Path,
    tenant_id: str,
    agent_id: str,
) -> AgentProfileConfig:
    """读取指定 agent 的 workspace/agent.json。"""
    root_config = load_root_config(swe_root, tenant_id)
    if agent_id not in root_config.agents.profiles:
        raise ValueError(f"Agent '{agent_id}' not found in config")

    agent_ref = root_config.agents.profiles[agent_id]
    workspace_dir = Path(agent_ref.workspace_dir).expanduser()
    agent_config_path = workspace_dir / "agent.json"

    if not agent_config_path.exists():
        raise FileNotFoundError(
            f"Agent config not found: {agent_config_path}",
        )

    with open(agent_config_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if "id" not in data:
        data["id"] = agent_id
    if "name" not in data:
        data["name"] = agent_id.title()

    return AgentProfileConfig.model_validate(data)


def save_agent_config(
    swe_root: Path,
    tenant_id: str,
    agent_id: str,
    agent_config: AgentProfileConfig,
) -> None:
    """保存指定 agent 的 workspace/agent.json。"""
    root_config = load_root_config(swe_root, tenant_id)
    if agent_id not in root_config.agents.profiles:
        raise ValueError(f"Agent '{agent_id}' not found in config")

    agent_ref = root_config.agents.profiles[agent_id]
    workspace_dir = Path(agent_ref.workspace_dir).expanduser()
    workspace_dir.mkdir(parents=True, exist_ok=True)
    agent_config_path = workspace_dir / "agent.json"

    with open(agent_config_path, "w", encoding="utf-8") as file:
        json.dump(
            agent_config.model_dump(mode="json", exclude_none=True),
            file,
            ensure_ascii=False,
            indent=2,
        )
