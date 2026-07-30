# -*- coding: utf-8 -*-
"""Source-tool catalogue records.

Published versions retain script content for controlled manager downloads.
Metadata objects intentionally omit it so normal catalogue/list/audit surfaces
cannot leak uploaded code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SourceToolVersion:
    """An immutable source-tool version, including controlled script content."""

    name: str
    version: int
    description: str
    json_schema: dict[str, Any]
    required_env: tuple[str, ...]
    content_digest: str
    script: str
    created_at: float
    created_by: str | None

    def metadata(self, *, active: bool) -> "SourceToolMetadata":
        """Create a script-free representation for ordinary responses."""
        return SourceToolMetadata(
            name=self.name,
            version=self.version,
            description=self.description,
            json_schema=self.json_schema,
            required_env=self.required_env,
            content_digest=self.content_digest,
            active=active,
            origin="source",
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to persistent JSON."""
        data = asdict(self)
        data["required_env"] = list(self.required_env)
        return data

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SourceToolVersion":
        """Restore a persisted version."""
        return cls(
            name=str(value["name"]),
            version=int(value["version"]),
            description=str(value["description"]),
            json_schema=dict(value["json_schema"]),
            required_env=tuple(value.get("required_env", ())),
            content_digest=str(value["content_digest"]),
            script=str(value["script"]),
            created_at=float(value["created_at"]),
            created_by=value.get("created_by"),
        )


@dataclass(frozen=True)
class SourceToolDraft:
    """The single unpublished draft for one source/tool-name pair."""

    name: str
    description: str
    json_schema: dict[str, Any]
    required_env: tuple[str, ...]
    content_digest: str
    script: str
    created_at: float
    created_by: str | None
    status: str = "draft"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to persistent JSON."""
        data = asdict(self)
        data["required_env"] = list(self.required_env)
        return data

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SourceToolDraft":
        """Restore a persisted draft."""
        return cls(
            name=str(value["name"]),
            description=str(value["description"]),
            json_schema=dict(value["json_schema"]),
            required_env=tuple(value.get("required_env", ())),
            content_digest=str(value["content_digest"]),
            script=str(value["script"]),
            created_at=float(value["created_at"]),
            created_by=value.get("created_by"),
            status="draft",
        )


@dataclass(frozen=True)
class SourceToolMetadata:
    """Script-free effective tool representation."""

    name: str
    version: int
    description: str
    json_schema: dict[str, Any]
    required_env: tuple[str, ...]
    content_digest: str
    active: bool
    origin: str


@dataclass(frozen=True)
class SourceToolAuditEvent:
    """Metadata-only audit event."""

    event: str
    source_id: str
    tool_name: str
    actor: str | None
    timestamp: float
    version: int | None = None
    content_digest: str | None = None
    tenant_id: str | None = None
    agent_id: str | None = None
    result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to persistent JSON."""
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SourceToolAuditEvent":
        """Restore a persisted audit event."""
        return cls(
            event=str(value["event"]),
            source_id=str(value["source_id"]),
            tool_name=str(value["tool_name"]),
            actor=value.get("actor"),
            timestamp=float(value["timestamp"]),
            version=(
                int(value["version"])
                if value.get("version") is not None
                else None
            ),
            content_digest=value.get("content_digest"),
            tenant_id=value.get("tenant_id"),
            agent_id=value.get("agent_id"),
            result=value.get("result"),
        )
