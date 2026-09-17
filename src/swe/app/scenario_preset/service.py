# -*- coding: utf-8 -*-
"""Scenario preset catalog business rules and effective-tree projection."""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol

from .models import (
    CatalogCapability,
    CatalogDomain,
    CatalogNode,
    CatalogNodeCreate,
    CatalogNodeMove,
    CatalogNodeReorder,
    CatalogNodeUpdate,
    CatalogScenario,
    EffectiveCatalog,
    NodeKind,
    ScenarioBindingsUpdate,
    ScenarioResourceBinding,
)


class ScenarioPresetStoreProtocol(Protocol):
    """Minimum read contract used by the effective catalog projection."""

    async def list_nodes(self, source_id: str) -> list[CatalogNode]:
        """Return all nodes for a single source."""

    async def get_node(
        self,
        source_id: str,
        node_id: str,
    ) -> CatalogNode | None:
        """Return a source-owned node."""

    async def create_node(self, node: CatalogNode) -> CatalogNode:
        """Persist a node."""

    async def update_node(self, node: CatalogNode) -> CatalogNode:
        """Persist editable node fields."""

    async def move_node(self, node: CatalogNode) -> CatalogNode:
        """Persist a parent move."""

    async def persist_sibling_order(
        self,
        source_id: str,
        parent_id: str | None,
        node_ids: list[str],
    ) -> None:
        """Persist a normalized sibling queue."""

    async def delete_node(self, source_id: str, node_id: str) -> None:
        """Delete a leaf node."""

    async def list_bindings(
        self,
        source_id: str,
        scenario_id: str,
    ) -> list[ScenarioResourceBinding]:
        """Return scenario bindings."""

    async def replace_bindings(
        self,
        source_id: str,
        scenario_id: str,
        bindings: list[ScenarioResourceBinding],
    ) -> None:
        """Persist scenario bindings."""

    def new_node_id(self) -> str:
        """Allocate a stable node ID."""


class ScenarioPresetCatalogService:
    """Projects strict catalog records into selectable, enabled paths."""

    def __init__(self, store: ScenarioPresetStoreProtocol):
        self.store = store

    async def get_effective_catalog(self, source_id: str) -> EffectiveCatalog:
        """Return only complete enabled domain-capability-scenario paths."""
        nodes = await self.store.list_nodes(source_id)
        children: dict[str | None, list[CatalogNode]] = defaultdict(list)
        for node in nodes:
            if node.is_active:
                children[node.parent_id].append(node)
        for sibling_nodes in children.values():
            sibling_nodes.sort(key=lambda item: (item.sort_order, item.id))

        domains: list[CatalogDomain] = []
        for domain in children[None]:
            if domain.kind is not NodeKind.DOMAIN:
                continue
            capabilities: list[CatalogCapability] = []
            for capability in children[domain.id]:
                if capability.kind is not NodeKind.CAPABILITY:
                    continue
                scenarios = [
                    CatalogScenario(**scenario.model_dump())
                    for scenario in children[capability.id]
                    if scenario.kind is NodeKind.SCENARIO
                ]
                if scenarios:
                    capabilities.append(
                        CatalogCapability(
                            **capability.model_dump(),
                            scenarios=scenarios,
                        ),
                    )
            if capabilities:
                domains.append(
                    CatalogDomain(
                        **domain.model_dump(),
                        capabilities=capabilities,
                    ),
                )
        return EffectiveCatalog(domains=domains)

    async def create_node(
        self,
        source_id: str,
        request: CatalogNodeCreate,
    ) -> CatalogNode:
        """Validate and append a catalog node at the end of its sibling queue."""
        nodes = await self.store.list_nodes(source_id)
        self._validate_requested_parent(nodes, request.kind, request.parent_id)
        self._ensure_unique_name(nodes, request.parent_id, request.name)
        node = CatalogNode(
            id=self.store.new_node_id(),
            source_id=source_id,
            kind=request.kind,
            parent_id=request.parent_id,
            name=request.name,
            prompt_draft=(
                request.prompt_draft
                if request.kind is NodeKind.SCENARIO
                else ""
            ),
            is_active=request.is_active,
            sort_order=1
            + sum(node.parent_id == request.parent_id for node in nodes),
        )
        return await self.store.create_node(node)

    async def update_node(
        self,
        source_id: str,
        node_id: str,
        request: CatalogNodeUpdate,
    ) -> CatalogNode:
        """Edit one node while preserving its identity and position."""
        nodes = await self.store.list_nodes(source_id)
        node = self._require_node(nodes, node_id)
        name = request.name.strip() if request.name is not None else node.name
        if name.casefold() != node.name.casefold():
            self._ensure_unique_name(
                nodes,
                node.parent_id,
                name,
                ignored_id=node.id,
            )
        prompt_draft = node.prompt_draft
        if request.prompt_draft is not None:
            if node.kind is not NodeKind.SCENARIO:
                raise ValueError("only scenario supports prompt_draft")
            prompt_draft = request.prompt_draft
        updated = node.model_copy(
            update={
                "name": name,
                "prompt_draft": prompt_draft,
                "is_active": (
                    node.is_active
                    if request.is_active is None
                    else request.is_active
                ),
            },
        )
        return await self.store.update_node(updated)

    async def move_node(
        self,
        source_id: str,
        node_id: str,
        request: CatalogNodeMove,
    ) -> CatalogNode:
        """Move a non-root node to a compatible parent and append it there."""
        nodes = await self.store.list_nodes(source_id)
        node = self._require_node(nodes, node_id)
        if node.kind is NodeKind.DOMAIN:
            raise ValueError("domain cannot be moved")
        self._validate_requested_parent(nodes, node.kind, request.parent_id)
        self._ensure_unique_name(
            nodes,
            request.parent_id,
            node.name,
            ignored_id=node.id,
        )
        destination = [
            item
            for item in nodes
            if item.parent_id == request.parent_id and item.id != node.id
        ]
        moved = node.model_copy(
            update={
                "parent_id": request.parent_id,
                "sort_order": len(destination) + 1,
            },
        )
        await self.store.move_node(moved)
        await self._normalize_siblings(
            source_id,
            nodes,
            node.parent_id,
            excluded_id=node.id,
        )
        return moved

    async def reorder_node(
        self,
        source_id: str,
        node_id: str,
        request: CatalogNodeReorder,
    ) -> CatalogNode:
        """Move one node inside its sibling queue."""
        nodes = await self.store.list_nodes(source_id)
        node = self._require_node(nodes, node_id)
        siblings = sorted(
            [
                item
                for item in nodes
                if item.parent_id == node.parent_id and item.id != node.id
            ],
            key=lambda item: (item.sort_order, item.id),
        )
        siblings.insert(min(request.sort_order - 1, len(siblings)), node)
        await self.store.persist_sibling_order(
            source_id,
            node.parent_id,
            [item.id for item in siblings],
        )
        return node.model_copy(update={"sort_order": siblings.index(node) + 1})

    async def delete_node(self, source_id: str, node_id: str) -> None:
        """Delete only a leaf; administrators must move/delete descendants first."""
        nodes = await self.store.list_nodes(source_id)
        node = self._require_node(nodes, node_id)
        if any(item.parent_id == node.id for item in nodes):
            raise ValueError("only leaf nodes can be deleted")
        await self.store.delete_node(source_id, node_id)
        await self._normalize_siblings(
            source_id,
            nodes,
            node.parent_id,
            excluded_id=node.id,
        )

    async def get_bindings(
        self,
        source_id: str,
        scenario_id: str,
    ) -> list[ScenarioResourceBinding]:
        """Read bindings only after proving the node is a scenario leaf."""
        node = await self.store.get_node(source_id, scenario_id)
        self._require_scenario(node)
        return await self.store.list_bindings(source_id, scenario_id)

    async def get_submittable_scenario(
        self,
        source_id: str,
        scenario_id: str,
    ) -> tuple[CatalogNode, list[ScenarioResourceBinding], CatalogNode]:
        """Revalidate an enabled scenario and all ancestors at first submit."""
        nodes = await self.store.list_nodes(source_id)
        scenario = self._require_node(nodes, scenario_id)
        if scenario.kind is not NodeKind.SCENARIO or not scenario.is_active:
            raise ValueError("scenario is unavailable")
        capability = next(
            (item for item in nodes if item.id == scenario.parent_id),
            None,
        )
        if (
            capability is None
            or capability.kind is not NodeKind.CAPABILITY
            or not capability.is_active
        ):
            raise ValueError("scenario is unavailable")
        domain = next(
            (item for item in nodes if item.id == capability.parent_id),
            None,
        )
        if (
            domain is None
            or domain.kind is not NodeKind.DOMAIN
            or not domain.is_active
        ):
            raise ValueError("scenario is unavailable")
        bindings = await self.store.list_bindings(source_id, scenario_id)
        return scenario, bindings, capability

    async def replace_bindings(
        self,
        source_id: str,
        scenario_id: str,
        request: ScenarioBindingsUpdate,
    ) -> None:
        """Replace bindings and require unique type/id pairs in the request."""
        node = await self.store.get_node(source_id, scenario_id)
        self._require_scenario(node)
        keys = {
            (item.resource_type, item.resource_id) for item in request.bindings
        }
        if len(keys) != len(request.bindings):
            raise ValueError("duplicate resource binding")
        bindings = [
            item.model_copy(update={"sort_order": index})
            for index, item in enumerate(request.bindings, start=1)
        ]
        await self.store.replace_bindings(source_id, scenario_id, bindings)

    @staticmethod
    def _require_node(nodes: list[CatalogNode], node_id: str) -> CatalogNode:
        for node in nodes:
            if node.id == node_id:
                return node
        raise ValueError("catalog node not found")

    @staticmethod
    def _require_scenario(node: CatalogNode | None) -> None:
        if node is None or node.kind is not NodeKind.SCENARIO:
            raise ValueError("scenario not found")

    @staticmethod
    def _validate_requested_parent(
        nodes: list[CatalogNode],
        kind: NodeKind,
        parent_id: str | None,
    ) -> None:
        if kind is NodeKind.DOMAIN:
            if parent_id is not None:
                raise ValueError("domain must not have parent")
            return
        parent = next((item for item in nodes if item.id == parent_id), None)
        expected_kind = (
            NodeKind.DOMAIN
            if kind is NodeKind.CAPABILITY
            else NodeKind.CAPABILITY
        )
        if parent is None or parent.kind is not expected_kind:
            raise ValueError("invalid catalog parent")

    @staticmethod
    def _ensure_unique_name(
        nodes: list[CatalogNode],
        parent_id: str | None,
        name: str,
        ignored_id: str | None = None,
    ) -> None:
        normalized = name.strip().casefold()
        if any(
            node.parent_id == parent_id
            and node.id != ignored_id
            and node.name.casefold() == normalized
            for node in nodes
        ):
            raise ValueError("duplicate sibling name")

    async def _normalize_siblings(
        self,
        source_id: str,
        nodes: list[CatalogNode],
        parent_id: str | None,
        excluded_id: str | None = None,
    ) -> None:
        siblings = sorted(
            [
                node
                for node in nodes
                if node.parent_id == parent_id and node.id != excluded_id
            ],
            key=lambda item: (item.sort_order, item.id),
        )
        await self.store.persist_sibling_order(
            source_id,
            parent_id,
            [item.id for item in siblings],
        )
