# -*- coding: utf-8 -*-
"""Database storage for source-owned scenario preset catalogs."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from .models import (
    CatalogNode,
    NodeKind,
    ScenarioResourceBinding,
    ScenarioResourceType,
)

logger = logging.getLogger(__name__)

_NODE_TABLE = "swe_scenario_preset_nodes"
_BINDING_TABLE = "swe_scenario_preset_bindings"


class ScenarioPresetStore:
    """Persist catalog nodes and ordered market-resource bindings."""

    def __init__(self, db: Any):
        self.db = db

    @property
    def is_available(self) -> bool:
        return self.db is not None and bool(
            getattr(self.db, "is_connected", False),
        )

    def _require_db(self) -> Any:
        if not self.is_available:
            raise RuntimeError("Scenario preset storage unavailable")
        return self.db

    async def initialize(self) -> None:
        """Create the catalog tables when the connected deployment supports it."""
        db = self._require_db()
        for query in _CREATE_TABLES:
            await db.execute(query)

    async def list_nodes(self, source_id: str) -> list[CatalogNode]:
        """List one Source's full tree in stable sibling order."""
        db = self._require_db()
        rows = await db.fetch_all(
            f"""
            SELECT id, source_id, node_kind, parent_id, name, prompt_draft,
                   sort_order, is_active
            FROM {_NODE_TABLE}
            WHERE source_id = %s
            ORDER BY parent_id IS NOT NULL, parent_id, sort_order, id
            """,
            (source_id,),
        )
        return [self._row_to_node(row) for row in rows]

    async def get_node(
        self,
        source_id: str,
        node_id: str,
    ) -> CatalogNode | None:
        """Fetch a node only from its owning Source."""
        db = self._require_db()
        row = await db.fetch_one(
            f"""
            SELECT id, source_id, node_kind, parent_id, name, prompt_draft,
                   sort_order, is_active
            FROM {_NODE_TABLE}
            WHERE source_id = %s AND id = %s
            """,
            (source_id, node_id),
        )
        return self._row_to_node(row) if row else None

    async def list_bindings(
        self,
        source_id: str,
        scenario_id: str,
    ) -> list[ScenarioResourceBinding]:
        """Return bindings only for a scenario within its owning Source."""
        db = self._require_db()
        rows = await db.fetch_all(
            f"""
            SELECT resource_id, resource_type, display_name, sort_order
            FROM {_BINDING_TABLE}
            WHERE source_id = %s AND scenario_id = %s
            ORDER BY resource_type, sort_order, resource_id
            """,
            (source_id, scenario_id),
        )
        return [
            ScenarioResourceBinding(
                resource_id=row["resource_id"],
                resource_type=ScenarioResourceType(row["resource_type"]),
                display_name=row["display_name"],
                sort_order=int(row["sort_order"]),
            )
            for row in rows
        ]

    async def create_node(self, node: CatalogNode) -> CatalogNode:
        """Append a node; parent validation is enforced by the service."""
        db = self._require_db()
        await db.execute(
            f"""
            INSERT INTO {_NODE_TABLE}
                (id, source_id, node_kind, parent_id, name, normalized_name,
                 prompt_draft, sort_order, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                node.id,
                node.source_id,
                node.kind.value,
                node.parent_id,
                node.name,
                _normalized_name(node.name),
                node.prompt_draft,
                node.sort_order,
                int(node.is_active),
            ),
        )
        return node

    async def update_node(self, node: CatalogNode) -> CatalogNode:
        """Persist editable fields without changing stable ID or parent."""
        db = self._require_db()
        await db.execute(
            f"""
            UPDATE {_NODE_TABLE}
            SET name = %s, normalized_name = %s, prompt_draft = %s,
                is_active = %s
            WHERE source_id = %s AND id = %s
            """,
            (
                node.name,
                _normalized_name(node.name),
                node.prompt_draft,
                int(node.is_active),
                node.source_id,
                node.id,
            ),
        )
        return node

    async def move_node(self, node: CatalogNode) -> CatalogNode:
        """Persist a compatible new parent and final destination order."""
        db = self._require_db()
        await db.execute(
            f"""
            UPDATE {_NODE_TABLE}
            SET parent_id = %s, sort_order = %s
            WHERE source_id = %s AND id = %s
            """,
            (node.parent_id, node.sort_order, node.source_id, node.id),
        )
        return node

    async def persist_sibling_order(
        self,
        source_id: str,
        parent_id: str | None,
        node_ids: list[str],
    ) -> None:
        """Rewrite one sibling queue to contiguous, deterministic positions."""
        db = self._require_db()
        for sort_order, node_id in enumerate(node_ids, start=1):
            await db.execute(
                f"""
                UPDATE {_NODE_TABLE}
                SET sort_order = %s
                WHERE source_id = %s AND id = %s
                  AND parent_id <=> %s
                """,
                (sort_order, source_id, node_id, parent_id),
            )

    async def delete_node(self, source_id: str, node_id: str) -> None:
        """Delete a leaf node and its resource bindings."""
        db = self._require_db()
        await db.execute(
            f"DELETE FROM {_BINDING_TABLE} WHERE source_id = %s AND scenario_id = %s",
            (source_id, node_id),
        )
        await db.execute(
            f"DELETE FROM {_NODE_TABLE} WHERE source_id = %s AND id = %s",
            (source_id, node_id),
        )

    async def replace_bindings(
        self,
        source_id: str,
        scenario_id: str,
        bindings: list[ScenarioResourceBinding],
    ) -> None:
        """Replace a scenario's ordered bindings without storing secret values."""
        db = self._require_db()
        await db.execute(
            f"DELETE FROM {_BINDING_TABLE} WHERE source_id = %s AND scenario_id = %s",
            (source_id, scenario_id),
        )
        for binding in bindings:
            await db.execute(
                f"""
                INSERT INTO {_BINDING_TABLE}
                    (source_id, scenario_id, resource_id, resource_type,
                     display_name, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    source_id,
                    scenario_id,
                    binding.resource_id,
                    binding.resource_type.value,
                    binding.display_name,
                    binding.sort_order,
                ),
            )

    @staticmethod
    def new_node_id() -> str:
        """Generate a non-semantic stable opaque node ID."""
        return uuid4().hex

    @staticmethod
    def _row_to_node(row: dict[str, Any]) -> CatalogNode:
        return CatalogNode(
            id=str(row["id"]),
            source_id=str(row["source_id"]),
            kind=NodeKind(row["node_kind"]),
            parent_id=row.get("parent_id"),
            name=row["name"],
            prompt_draft=row.get("prompt_draft") or "",
            sort_order=int(row["sort_order"]),
            is_active=bool(row["is_active"]),
        )


def _normalized_name(name: str) -> str:
    return name.strip().casefold()


_CREATE_TABLES = (
    f"""
    CREATE TABLE IF NOT EXISTS {_NODE_TABLE} (
        id VARCHAR(64) PRIMARY KEY,
        source_id VARCHAR(64) NOT NULL,
        node_kind VARCHAR(16) NOT NULL,
        parent_id VARCHAR(64) NULL,
        parent_key VARCHAR(64) AS (IFNULL(parent_id, '')) STORED,
        name VARCHAR(128) NOT NULL,
        normalized_name VARCHAR(128) NOT NULL,
        prompt_draft TEXT NOT NULL,
        sort_order INT NOT NULL,
        is_active TINYINT(1) NOT NULL DEFAULT 1,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_scenario_preset_sibling_name
            (source_id, parent_key, normalized_name),
        KEY idx_scenario_preset_children (source_id, parent_id, sort_order)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {_BINDING_TABLE} (
        source_id VARCHAR(64) NOT NULL,
        scenario_id VARCHAR(64) NOT NULL,
        resource_id VARCHAR(128) NOT NULL,
        resource_type VARCHAR(16) NOT NULL,
        display_name VARCHAR(256) NOT NULL,
        sort_order INT NOT NULL,
        PRIMARY KEY (source_id, scenario_id, resource_type, resource_id),
        KEY idx_scenario_preset_bindings (source_id, scenario_id, sort_order)
    )
    """,
)
