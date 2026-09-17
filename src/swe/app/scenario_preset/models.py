# -*- coding: utf-8 -*-
"""Models for the source-owned scenario preset catalog."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class NodeKind(StrEnum):
    """One level in the fixed capability catalog hierarchy."""

    DOMAIN = "domain"
    CAPABILITY = "capability"
    SCENARIO = "scenario"


class CatalogNode(BaseModel):
    """Persistent catalog node with a stable source-wide identifier."""

    id: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=64)
    kind: NodeKind
    parent_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    prompt_draft: str = ""
    sort_order: int = Field(ge=1)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_parent(self) -> "CatalogNode":
        if self.kind is NodeKind.DOMAIN and self.parent_id is not None:
            raise ValueError("domain must not have parent_id")
        if self.kind is not NodeKind.DOMAIN and not self.parent_id:
            raise ValueError("parent_id is required for non-domain nodes")
        if self.kind is not NodeKind.SCENARIO and self.prompt_draft:
            raise ValueError("only scenario may have prompt_draft")
        return self


class ScenarioResourceType(StrEnum):
    """Marketplace resources that a scenario can request at submit time."""

    SKILL = "skill"
    MCP_SERVICE = "mcp_service"


class ScenarioResourceBinding(BaseModel):
    """A stable marketplace resource identity attached to one scenario."""

    resource_id: str = Field(min_length=1, max_length=128)
    resource_type: ScenarioResourceType
    display_name: str = Field(min_length=1, max_length=256)
    sort_order: int = Field(ge=1)


class CatalogScenario(CatalogNode):
    """Leaf returned to the new-chat selector."""

    kind: NodeKind = NodeKind.SCENARIO


class CatalogCapability(CatalogNode):
    """Second-level node returned with its selectable scenarios."""

    kind: NodeKind = NodeKind.CAPABILITY
    scenarios: list[CatalogScenario] = Field(default_factory=list)


class CatalogDomain(CatalogNode):
    """Top-level node returned with complete enabled descendant paths."""

    kind: NodeKind = NodeKind.DOMAIN
    capabilities: list[CatalogCapability] = Field(default_factory=list)


class EffectiveCatalog(BaseModel):
    """Read model for new chat; omitted branches are not selectable."""

    domains: list[CatalogDomain] = Field(default_factory=list)


class CatalogNodeCreate(BaseModel):
    """Administrator request to append one node to a valid parent."""

    kind: NodeKind
    parent_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    prompt_draft: str = ""
    is_active: bool = True


class CatalogNodeUpdate(BaseModel):
    """Administrator content and activation update."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    prompt_draft: str | None = None
    is_active: bool | None = None


class CatalogNodeMove(BaseModel):
    """Move a capability or scenario to a compatible destination parent."""

    parent_id: str = Field(min_length=1, max_length=64)


class CatalogNodeReorder(BaseModel):
    """Move a node to one absolute position among its siblings."""

    sort_order: int = Field(ge=1)


class ScenarioBindingsUpdate(BaseModel):
    """Replace one scenario's ordered market resource bindings."""

    bindings: list[ScenarioResourceBinding] = Field(default_factory=list)
