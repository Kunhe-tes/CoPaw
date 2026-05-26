# -*- coding: utf-8 -*-
"""API 请求/响应模型."""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class PublishSkillRequest(BaseModel):
    """上架技能请求体."""

    name: str
    description: str = ""
    creator_id: str
    creator_name: str = ""
    category_id: Optional[int] = None
    bbk_ids: list[str] = Field(default_factory=list)
    skill_json: dict = Field(default_factory=dict)
    skill_md: str = ""
    # 可选：指定用户技能目录名，用于同步整个目录
    skill_name: Optional[str] = None
    agent_id: str = "default"


class DistributeRequest(BaseModel):
    """分发技能请求体."""

    target_type: Literal["all", "bbk_id", "user_id"]
    target_values: list[str] = Field(default_factory=list)


class MarketSkillResponse(BaseModel):
    """市场技能列表/详情响应."""

    item_id: str
    name: str
    description: str
    version: str
    creator_id: str
    creator_name: str
    category_id: Optional[int]
    bbk_ids: list[str]
    status: str
    created_at: Optional[str]
    updated_at: Optional[str]
    call_count: int = 0
    user_count: int = 0


class SkillUserStat(BaseModel):
    """技能详情页调用客户明细."""

    user_id: str
    user_name: str
    call_count: int


class MarketSkillDetail(MarketSkillResponse):
    """技能详情（含调用客户明细）."""

    user_stats: list[SkillUserStat] = Field(default_factory=list)


class MySkillItem(BaseModel):
    """我的技能列表条目."""

    skill_name: str  # 目录名，用于 API 操作标识
    display_name: str = ""  # 展示名称，从 skill.json 的 name 字段读取
    source: str
    description: str = ""
    version: Optional[str] = None
    received_version: Optional[str] = None
    distributed_by: Optional[str] = None
    is_received: bool = False
    has_update: bool = False
    enabled: bool = True
    category: Optional[str] = None
    creator_name: Optional[str] = None
    created_at: Optional[str] = None  # 技能创建/接收时间
    updated_at: Optional[str] = None  # 技能最后更新时间


class BatchOperationRequest(BaseModel):
    """批量操作请求."""

    skills: list[str]


class SkillOperationResult(BaseModel):
    """单个技能操作结果."""

    skill_name: str
    success: bool
    reason: str | None = None


class BatchOperationResponse(BaseModel):
    """批量操作响应."""

    results: dict[str, Any]
    success_count: int
    failed_count: int


class DistributeConflictItem(BaseModel):
    """分发冲突明细."""

    user_id: str
    skill_name: str
    reason: str


class DistributeResponse(BaseModel):
    """分发结果."""

    distributed_count: int
    conflict_count: int = 0
    conflicts: list[DistributeConflictItem] = []
    item_id: str


class FileTreeNode(BaseModel):
    """文件树节点."""

    name: str
    type: Literal["file", "directory"]
    path: str
    children: list["FileTreeNode"] | None = None


class FileContentResponse(BaseModel):
    """文件内容响应."""

    content: str
    file_type: str  # "markdown" | "json" | "text" | "binary"


class OperationResponse(BaseModel):
    """操作结果响应."""

    success: bool = True
    message: str | None = None


class UploadSkillResponse(BaseModel):
    """技能上传响应."""

    imported: list[str] = Field(default_factory=list)
    count: int = 0
    enabled: bool = True
    name: str | None = None
    description: str | None = None
    conflicts: list[dict] | None = None


class MCPDistributionRequest(BaseModel):
    """MCP 分发请求体，语义与现有 MCP 菜单分发到租户保持一致。"""

    target_tenant_ids: list[str] = Field(default_factory=list)
    overwrite: bool = True


class MCPDistributionTenantResult(BaseModel):
    """单个租户的 MCP 分发结果。"""

    tenant_id: str
    success: bool
    bootstrapped: bool = False
    default_agent_updated: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class MCPDistributionResponse(BaseModel):
    """MCP 分发响应。"""

    source_agent_id: str
    results: list[MCPDistributionTenantResult] = Field(default_factory=list)


class MarketMCPItem(BaseModel):
    """市场 MCP 列表项."""

    item_id: str
    client_key: str
    name: str
    chinese_name: str = ""
    description: str = ""
    guidance: str = ""
    version: str = "1.0.0"
    creator_id: str
    creator_name: str = ""
    category_id: Optional[int] = None
    bbk_ids: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    call_count: int = 0
    user_count: int = 0


class MCPConfigDetail(BaseModel):
    """MCP 配置详情."""

    transport: str = "stdio"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str = ""
    lazy_load: bool = False


class MCPUserStat(BaseModel):
    """MCP 用户统计."""

    user_id: str
    user_name: str
    call_count: int


class MarketMCPDetail(MarketMCPItem):
    """市场 MCP 详情."""

    config: MCPConfigDetail
    user_stats: list[MCPUserStat] = Field(default_factory=list)


class PublishMCPRequest(BaseModel):
    """发布 MCP 到市场请求."""

    client_key: str
    name: str
    chinese_name: str = ""
    description: str = ""
    guidance: str = ""
    creator_id: str
    creator_name: str = ""
    category_id: Optional[int] = None
    bbk_ids: list[str] = Field(default_factory=list)
    config: dict


class UploadMCPResponse(BaseModel):
    """上传 MCP 响应."""

    success: bool
    error: Optional[str] = None


class UpdateMarketMCPMetadataRequest(BaseModel):
    """MCP 市场元数据更新请求体。"""

    chinese_name: str | None = None
    description: str | None = None
    guidance: str | None = None
    bbk_ids: list[str] = Field(default_factory=list)


class DistributionRecord(BaseModel):
    """分发记录."""

    target_user_id: str
    target_user_name: str = ""
    target_bbk_id: str = ""
    distributed_at: Optional[str] = None


class RecallRequest(BaseModel):
    """撤回请求体."""

    target_user_ids: list[str] | None = None  # 不传则撤回所有
    force: bool = False  # 强制撤回，不验证来源是否匹配
    skill_name: str | None = None  # 按技能名称撤回（技能专用）
    mcp_name: str | None = None  # 按 MCP 名称撤回（MCP 专用）


class RecallResultItem(BaseModel):
    """单个用户的撤回结果."""

    user_id: str
    success: bool
    reason: str | None = None


class RecallResponse(BaseModel):
    """撤回结果响应."""

    recalled_count: int
    failed_count: int = 0
    results: list[RecallResultItem] = Field(default_factory=list)
    item_id: str
