# Run-scoped SubAgent Definitions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign SubAgent start and registration so the Main Agent can start run-scoped SubAgents with compact `name`/`instruction`/`objective` input, while stored/built-in definitions can be registered, matched deterministically, and surfaced with stable run metadata.

**Architecture:** Replace the old `agent_name`/`prompt.system` definition vocabulary with `name`/`instruction`/`output_contract` and introduce three definition sources: `builtin`, `stored`, and `run_scoped`. Add a tenant-and-agent scoped definition service that stores reusable definitions as per-definition JSON files, performs deterministic short-circuit matching, and falls back to a run-scoped definition for every valid compact start request. Keep `start_subagent` compact and move full metadata, budget, and registration concerns into a management-facing registration tool.

**Tech Stack:** Python 3, Pydantic models, Agentscope tool functions, pytest, local JSON stores, existing SubAgent supervisor/runtime/monitor modules.

---

## File Structure

**Modify:**
- `src/swe/app/subagents/models.py` - redefine `SubAgentDefinition`, `DelegationSpec`, budget, start request, registration request, match metadata, and run record fields.
- `src/swe/app/subagents/builtins.py` - migrate built-ins to `instruction`, top-level `task_types`, `trigger_keywords`, `priority`, and `output_contract`.
- `src/swe/app/subagents/registry.py` - update source validation and disallow stored definitions shadowing built-ins.
- `src/swe/app/subagents/run_store.py` - persist `nickname`, `start_request`, and `definition_match` on run records.
- `src/swe/app/subagents/supervisor.py` - start runs from resolved definitions and support run-scoped fallback metadata.
- `src/swe/app/subagents/runtime.py` - read `definition.instruction`, remove `max_tokens`, and keep AgentResult output contract hardening.
- `src/swe/agents/tools/subagent_background.py` - replace `start_subagent(agent_name, objective, ...)` with compact `start_subagent(name, instruction, objective, background="")`; add `register_subagent_definition`.
- `src/swe/agents/react_agent.py` - register the new registration tool only for explicit registration intent, not ordinary SubAgent intent.
- `src/swe/app/subagents/monitor.py` - include run nickname and match metadata in snapshots.
- `src/swe/app/routers/subagents.py` - return monitor snapshots with the new fields.
- `src/swe/app/subagents/__init__.py` - export new service/store/request/matcher types.

**Create:**
- `src/swe/app/subagents/definition_store.py` - per-definition JSON persistence for tenant+agent scoped stored definitions.
- `src/swe/app/subagents/definition_service.py` - normalize, validate, register, resolve, match, and build run-scoped definitions.
- `src/swe/app/subagents/matcher.py` - deterministic definition matcher and score explanations.
- `src/swe/app/subagents/nicknames.py` - built-in nickname pool and runtime assignment helper.

**Test:**
- `tests/unit/subagents/test_models_registry_policy.py`
- `tests/unit/subagents/test_definition_store_service.py`
- `tests/unit/subagents/test_definition_matcher.py`
- `tests/unit/subagents/test_background_tools.py`
- `tests/unit/subagents/test_background_supervisor.py`
- `tests/unit/subagents/test_runtime_and_delegation.py`
- `tests/unit/subagents/test_background_run_store.py`
- `tests/unit/subagents/test_monitor_api.py`
- `tests/unit/subagents/test_react_agent_and_guard_integration.py`

---

### Task 1: Model Migration

**Files:**
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/app/subagents/builtins.py`
- Modify: `src/swe/app/subagents/registry.py`
- Test: `tests/unit/subagents/test_models_registry_policy.py`

- [ ] **Step 1: Run GitNexus impact before editing model symbols**

Use GitNexus impact on:
- `SubAgentDefinition` in `src/swe/app/subagents/models.py`
- `DelegationSpec` in `src/swe/app/subagents/models.py`
- `BudgetConfig` in `src/swe/app/subagents/models.py`
- `builtin_definition_provider` in `src/swe/app/subagents/builtins.py`

Expected: review direct callers before editing. If GitNexus cannot resolve these symbols, record that result and continue with focused tests because this branch currently has incomplete SubAgent symbol indexing.

- [ ] **Step 2: Write failing tests for the new model vocabulary**

Update `tests/unit/subagents/test_models_registry_policy.py` with tests equivalent to:

```python
def test_definition_uses_instruction_and_top_level_routing_fields() -> None:
    definition = SubAgentDefinition.model_validate(
        {
            "name": "customer-aum-analyst",
            "source": "stored",
            "description": "Analyzes 1M AUM customer maintenance strategy.",
            "instruction": "Act as a customer strategy analyst.",
            "trigger_keywords": ["AUM", "客户维护"],
            "task_types": ["research", "analysis"],
            "priority": 20,
        },
    )

    assert definition.name == "customer-aum-analyst"
    assert definition.instruction == "Act as a customer strategy analyst."
    assert definition.output_contract == "Return only valid AgentResult JSON."
    assert definition.trigger_keywords == ["AUM", "客户维护"]
    assert definition.task_types == ["research", "analysis"]
    assert definition.priority == 20
    assert definition.source == "stored"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "name": "legacy",
            "source": "stored",
            "description": "legacy",
            "system_prompt": "legacy",
        },
        {
            "name": "legacy",
            "source": "stored",
            "description": "legacy",
            "prompt": {"system": "legacy"},
        },
        {
            "agent_name": "legacy",
            "source": "stored",
            "description": "legacy",
            "instruction": "legacy",
        },
    ],
)
def test_definition_rejects_legacy_field_names(payload: dict) -> None:
    with pytest.raises(ValidationError):
        SubAgentDefinition.model_validate(payload)


def test_budget_does_not_accept_max_tokens() -> None:
    with pytest.raises(ValidationError):
        BudgetConfig.model_validate({"max_tokens": 1000})
```

- [ ] **Step 3: Run the focused model tests and verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_models_registry_policy.py::test_definition_uses_instruction_and_top_level_routing_fields tests/unit/subagents/test_models_registry_policy.py::test_definition_rejects_legacy_field_names tests/unit/subagents/test_models_registry_policy.py::test_budget_does_not_accept_max_tokens -q
```

Expected: fail because the current model still uses `prompt.system`, `agent_name`, `routing`, and `max_tokens`.

- [ ] **Step 4: Update `models.py` with the new schema**

Implement these model changes:

```python
DefinitionSource = Literal["builtin", "stored", "run_scoped"]


class BudgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_turns: int = 6
    max_tool_calls: int = 30
    timeout_ms: int = 120000


class SubAgentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str = "1.0.0"
    schema_version: str = "subagent.definition.v2"
    source: DefinitionSource = "builtin"
    owner_scope: str = "builtin"
    enabled: bool = True
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)
    created_by: str | None = None
    nickname: str | None = None
    description: str
    role: str = "researcher"
    instruction: str
    output_contract: str = "Return only valid AgentResult JSON."
    model: ModelRouting = Field(default_factory=ModelRouting)
    tools: ToolSet = Field(default_factory=ToolSet)
    permission: PermissionPolicy = Field(default_factory=PermissionPolicy)
    isolation: IsolationConfig = Field(default_factory=IsolationConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    task_types: list[str] = Field(default_factory=list)
    trigger_keywords: list[str] = Field(default_factory=list)
    priority: int = 100
    lifecycle: LifecycleConfig = Field(default_factory=LifecycleConfig)
```

Add validators:

```python
@field_validator("name", "description", "instruction", mode="after")
@classmethod
def _non_empty_string(cls, value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("field must be non-empty")
    return value


@field_validator("instruction")
@classmethod
def _instruction_size(cls, value: str) -> str:
    if len(value.encode("utf-8")) > 8192:
        raise ValueError("instruction exceeds 8192 bytes")
    return value


@field_validator("description")
@classmethod
def _description_size(cls, value: str) -> str:
    if len(value.encode("utf-8")) > 1024:
        raise ValueError("description exceeds 1024 bytes")
    return value


@field_validator("output_contract")
@classmethod
def _output_contract_size(cls, value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("output_contract must be non-empty")
    if len(value.encode("utf-8")) > 2048:
        raise ValueError("output_contract exceeds 2048 bytes")
    return value
```

Update list validators for `trigger_keywords` and `task_types`:

```python
def _validate_limited_string_list(
    values: list[str],
    *,
    field_name: str,
    max_items: int,
) -> list[str]:
    if len(values) > max_items:
        raise ValueError(f"{field_name} has too many items")
    cleaned: list[str] = []
    for value in values:
        item = value.strip()
        if not item:
            raise ValueError(f"{field_name} contains an empty item")
        if len(item) > 64:
            raise ValueError(f"{field_name} item exceeds 64 characters")
        cleaned.append(item)
    return cleaned
```

Update `DelegationSpec`:

```python
class DelegationSpec(BaseModel):
    task_id: str = Field(default_factory=lambda: f"task-{uuid4().hex[:12]}")
    parent_thread_id: str = ""
    name: str
    objective: str
    background: str = ""
    mode_context: ModeContext = Field(default_factory=ModeContext)
    scope: ScopeConfig = Field(default_factory=ScopeConfig)
    constraints: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    evidence_requirements: list[EvidenceRequirement] = Field(default_factory=list)
    expected_output: ExpectedOutput = Field(default_factory=ExpectedOutput)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    return_policy: ReturnPolicy = Field(default_factory=ReturnPolicy)
```

Add compact and registration models:

```python
class SubAgentStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    instruction: str
    objective: str
    background: str = ""


class SubAgentRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    instruction: str
    description: str
    nickname: str | None = None
    trigger_keywords: list[str] = Field(default_factory=list)
    task_types: list[str] = Field(default_factory=list)
    priority: int = 100
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    output_contract: str = "Return only valid AgentResult JSON."
    enabled: bool = True
```

Add match metadata:

```python
class DefinitionMatchMetadata(BaseModel):
    matched: bool = False
    definition_name: str | None = None
    definition_source: DefinitionSource | None = None
    score: float | None = None
    reason: str | None = None
```

- [ ] **Step 5: Migrate built-in definitions**

Change `src/swe/app/subagents/builtins.py` so `_builtin(...)` builds top-level fields:

```python
def _builtin(
    *,
    name: str,
    description: str,
    instruction: str,
    task_types: list[str],
    trigger_keywords: list[str],
    priority: int = 100,
) -> SubAgentDefinition:
    return SubAgentDefinition.model_validate(
        {
            "name": name,
            "version": "1.0.0",
            "source": "builtin",
            "owner_scope": "builtin",
            "description": description,
            "role": "researcher",
            "instruction": instruction,
            "output_contract": "Return only valid AgentResult JSON.",
            "tools": {
                "allow": [
                    "execute_shell_command",
                    "read_file",
                    "grep_search",
                    "glob_search",
                    "get_current_time",
                ],
            },
            "permission": PermissionPolicy.readonly().model_dump(mode="json"),
            "isolation": {
                "context": "fresh",
                "workspace": "shared",
                "memory": "none",
                "skills_enabled": False,
                "mcp_enabled": False,
            },
            "lifecycle": {
                "resumable": False,
                "cancellable": True,
                "allow_nested_delegation": False,
            },
            "task_types": task_types,
            "trigger_keywords": trigger_keywords,
            "priority": priority,
        },
    )
```

- [ ] **Step 6: Update registry source/shadowing rules**

Change `src/swe/app/subagents/registry.py` so source handling uses `stored`, not `user`:

```python
if definition.source == "builtin":
    if definition.name in stored_names:
        raise DefinitionValidationError(
            "stored definition cannot shadow builtin "
            f"SubAgent definition: {definition.name}",
        )
    builtin_names.add(definition.name)
elif definition.source == "stored":
    if definition.name in builtin_names:
        raise DefinitionValidationError(
            "stored definition cannot shadow builtin "
            f"SubAgent definition: {definition.name}",
        )
    stored_names.add(definition.name)
```

Do not load `run_scoped` definitions into the long-lived registry.

- [ ] **Step 7: Run model and registry tests**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_models_registry_policy.py -q
```

Expected: pass.

- [ ] **Step 8: Commit Task 1**

```bash
git add src/swe/app/subagents/models.py src/swe/app/subagents/builtins.py src/swe/app/subagents/registry.py tests/unit/subagents/test_models_registry_policy.py
git commit -m "refactor(subagents): adopt instruction-based definitions"
```

---

### Task 2: Store And Service

**Files:**
- Create: `src/swe/app/subagents/definition_store.py`
- Create: `src/swe/app/subagents/definition_service.py`
- Create: `src/swe/app/subagents/nicknames.py`
- Modify: `src/swe/app/subagents/__init__.py`
- Test: `tests/unit/subagents/test_definition_store_service.py`

- [ ] **Step 1: Write failing store/service tests**

Create `tests/unit/subagents/test_definition_store_service.py`:

```python
# -*- coding: utf-8 -*-
"""Stored SubAgent definition store and service tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swe.app.subagents import (
    AgentRegistry,
    SubAgentDefinitionService,
    SubAgentDefinitionStore,
    SubAgentRegistrationRequest,
    builtin_definition_provider,
)


def _request(name: str = "aum-customer-analyst") -> SubAgentRegistrationRequest:
    return SubAgentRegistrationRequest.model_validate(
        {
            "name": name,
            "instruction": "Act as a customer strategy analyst.",
            "description": "Analyzes 1M AUM customer maintenance strategy.",
            "trigger_keywords": ["AUM", "客户维护"],
            "task_types": ["research", "analysis"],
            "priority": 20,
            "budget": {
                "max_turns": 4,
                "max_tool_calls": 20,
                "timeout_ms": 60000,
            },
        },
    )


def test_store_writes_one_json_file_per_definition(tmp_path: Path) -> None:
    store = SubAgentDefinitionStore(tmp_path)
    definition = SubAgentDefinitionService(
        store=store,
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    ).build_stored_definition(_request())

    result = store.upsert(definition)

    assert result.created is True
    path = tmp_path / "aum-customer-analyst.json"
    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["name"] == "aum-customer-analyst"
    assert saved["source"] == "stored"
    assert "nickname" not in saved or saved["nickname"] is None


def test_service_upsert_reports_registered_then_updated(tmp_path: Path) -> None:
    service = SubAgentDefinitionService(
        store=SubAgentDefinitionStore(tmp_path),
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )

    first = service.register(_request())
    second = service.register(_request())

    assert first == {"status": "registered", "name": "aum-customer-analyst"}
    assert second == {"status": "updated", "name": "aum-customer-analyst"}


def test_service_rejects_builtin_name_conflict(tmp_path: Path) -> None:
    service = SubAgentDefinitionService(
        store=SubAgentDefinitionStore(tmp_path),
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )

    result = service.register(_request("risk-reviewer"))

    assert result == {
        "status": "failed",
        "reason": "builtin_name_conflict",
        "name": "risk-reviewer",
    }


def test_registration_budget_can_only_narrow_defaults(tmp_path: Path) -> None:
    service = SubAgentDefinitionService(
        store=SubAgentDefinitionStore(tmp_path),
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
    )

    with pytest.raises(ValueError, match="max_turns"):
        service.build_stored_definition(
            SubAgentRegistrationRequest.model_validate(
                {
                    "name": "too-large",
                    "instruction": "Act as an analyst.",
                    "description": "Too large budget.",
                    "budget": {"max_turns": 7},
                },
            ),
        )
```

- [ ] **Step 2: Run store/service tests and verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_definition_store_service.py -q
```

Expected: fail because the store/service modules do not exist.

- [ ] **Step 3: Implement nickname pool**

Create `src/swe/app/subagents/nicknames.py`:

```python
# -*- coding: utf-8 -*-
"""Runtime SubAgent nickname assignment."""

from __future__ import annotations

import random

BUILTIN_SUBAGENT_NICKNAMES = (
    "研究员",
    "分析员",
    "洞察助手",
    "策略顾问",
    "风险观察员",
)


def assign_subagent_nickname(configured: str | None = None) -> str:
    """Return a configured nickname or a random runtime display nickname."""
    if configured and configured.strip():
        return configured.strip()
    return random.choice(BUILTIN_SUBAGENT_NICKNAMES)
```

- [ ] **Step 4: Implement per-definition JSON store**

Create `src/swe/app/subagents/definition_store.py`:

```python
# -*- coding: utf-8 -*-
"""Tenant-and-agent scoped stored SubAgent definition persistence."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from .models import SubAgentDefinition


@dataclass(frozen=True)
class DefinitionUpsertResult:
    created: bool
    definition: SubAgentDefinition


class SubAgentDefinitionStore:
    """One JSON file per stored SubAgent definition."""

    def __init__(self, root: Path):
        self._root = Path(root)

    def list_definitions(self) -> list[SubAgentDefinition]:
        if not self._root.exists():
            return []
        definitions: list[SubAgentDefinition] = []
        for path in sorted(self._root.glob("*.json")):
            definitions.append(
                SubAgentDefinition.model_validate_json(
                    path.read_text(encoding="utf-8"),
                ),
            )
        return definitions

    def get(self, name: str) -> SubAgentDefinition | None:
        path = self._path_for_name(name)
        if not path.exists():
            return None
        return SubAgentDefinition.model_validate_json(
            path.read_text(encoding="utf-8"),
        )

    def upsert(self, definition: SubAgentDefinition) -> DefinitionUpsertResult:
        path = self._path_for_name(definition.name)
        created = not path.exists()
        self._root.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(definition.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return DefinitionUpsertResult(created=created, definition=definition)

    def _path_for_name(self, name: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip()) or "definition"
        return self._root / f"{safe}.json"
```

- [ ] **Step 5: Implement definition service**

Create `src/swe/app/subagents/definition_service.py`:

```python
# -*- coding: utf-8 -*-
"""Stored and run-scoped SubAgent definition service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .definition_store import SubAgentDefinitionStore
from .models import (
    BudgetConfig,
    DefinitionMatchMetadata,
    SubAgentDefinition,
    SubAgentRegistrationRequest,
    SubAgentStartRequest,
)
from .registry import AgentRegistry

DEFAULT_OUTPUT_CONTRACT = "Return only valid AgentResult JSON."


class SubAgentDefinitionService:
    """Normalize, validate, register, and build SubAgent definitions."""

    def __init__(
        self,
        *,
        store: SubAgentDefinitionStore,
        builtin_registry: AgentRegistry,
        owner_scope: str = "stored",
    ):
        self._store = store
        self._builtin_registry = builtin_registry
        self._owner_scope = owner_scope

    def register(self, request: SubAgentRegistrationRequest) -> dict[str, Any]:
        if self._builtin_name_exists(request.name):
            return {
                "status": "failed",
                "reason": "builtin_name_conflict",
                "name": request.name,
            }
        definition = self.build_stored_definition(request)
        result = self._store.upsert(definition)
        return {
            "status": "registered" if result.created else "updated",
            "name": definition.name,
        }

    def build_stored_definition(
        self,
        request: SubAgentRegistrationRequest,
    ) -> SubAgentDefinition:
        self._validate_budget(request.budget)
        return SubAgentDefinition.model_validate(
            {
                "name": request.name,
                "source": "stored",
                "owner_scope": self._owner_scope,
                "enabled": request.enabled,
                "nickname": request.nickname,
                "description": request.description,
                "instruction": request.instruction,
                "output_contract": request.output_contract or DEFAULT_OUTPUT_CONTRACT,
                "trigger_keywords": request.trigger_keywords,
                "task_types": request.task_types,
                "priority": request.priority,
                "budget": request.budget.model_dump(mode="json"),
            },
        )

    def build_run_scoped_definition(
        self,
        request: SubAgentStartRequest,
        *,
        owner_scope: str,
    ) -> SubAgentDefinition:
        return SubAgentDefinition.model_validate(
            {
                "name": request.name,
                "version": "run-scoped",
                "source": "run_scoped",
                "owner_scope": owner_scope,
                "description": request.objective[:1024],
                "instruction": request.instruction,
                "output_contract": DEFAULT_OUTPUT_CONTRACT,
                "budget": BudgetConfig().model_dump(mode="json"),
            },
        )

    def list_available_definitions(self) -> list[SubAgentDefinition]:
        return [
            definition
            for definition in self._store.list_definitions()
            + self._builtin_registry.list()
            if definition.enabled
        ]

    def _builtin_name_exists(self, name: str) -> bool:
        try:
            self._builtin_registry.resolve(name)
            return True
        except KeyError:
            return False

    def _validate_budget(self, budget: BudgetConfig) -> None:
        defaults = BudgetConfig()
        if budget.max_turns > defaults.max_turns:
            raise ValueError("max_turns cannot exceed default")
        if budget.max_tool_calls > defaults.max_tool_calls:
            raise ValueError("max_tool_calls cannot exceed default")
        if budget.timeout_ms > defaults.timeout_ms:
            raise ValueError("timeout_ms cannot exceed default")
```

- [ ] **Step 6: Export service/store types**

Modify `src/swe/app/subagents/__init__.py`:

```python
from .definition_service import SubAgentDefinitionService
from .definition_store import DefinitionUpsertResult, SubAgentDefinitionStore
from .nicknames import assign_subagent_nickname
```

Add these names to `__all__`.

- [ ] **Step 7: Run store/service tests**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_definition_store_service.py -q
```

Expected: pass.

- [ ] **Step 8: Commit Task 2**

```bash
git add src/swe/app/subagents/definition_store.py src/swe/app/subagents/definition_service.py src/swe/app/subagents/nicknames.py src/swe/app/subagents/__init__.py tests/unit/subagents/test_definition_store_service.py
git commit -m "feat(subagents): add stored definition service"
```

---

### Task 3: Deterministic Matcher

**Files:**
- Create: `src/swe/app/subagents/matcher.py`
- Modify: `src/swe/app/subagents/definition_service.py`
- Modify: `src/swe/app/subagents/__init__.py`
- Test: `tests/unit/subagents/test_definition_matcher.py`

- [ ] **Step 1: Write failing matcher tests**

Create `tests/unit/subagents/test_definition_matcher.py`:

```python
# -*- coding: utf-8 -*-
"""Deterministic SubAgent definition matcher tests."""

from __future__ import annotations

from datetime import datetime, timezone

from swe.app.subagents import (
    SubAgentDefinition,
    SubAgentDefinitionMatcher,
    SubAgentStartRequest,
)


def _definition(
    name: str,
    *,
    source: str = "stored",
    priority: int = 100,
    enabled: bool = True,
    trigger_keywords: list[str] | None = None,
    task_types: list[str] | None = None,
    description: str = "Research analyst.",
) -> SubAgentDefinition:
    return SubAgentDefinition.model_validate(
        {
            "name": name,
            "source": source,
            "enabled": enabled,
            "description": description,
            "instruction": f"Act as {name}.",
            "trigger_keywords": trigger_keywords or [],
            "task_types": task_types or [],
            "priority": priority,
            "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        },
    )


def _request(
    name: str = "research analyst",
    objective: str = "Analyze 1M AUM customer maintenance.",
) -> SubAgentStartRequest:
    return SubAgentStartRequest.model_validate(
        {
            "name": name,
            "instruction": "Act as a customer strategy analyst.",
            "objective": objective,
            "background": "Need AUM and 客户维护 advice.",
        },
    )


def test_exact_name_match_short_circuits() -> None:
    matcher = SubAgentDefinitionMatcher()
    result = matcher.match(_request("risk-reviewer"), [_definition("risk-reviewer")])

    assert result is not None
    assert result.definition.name == "risk-reviewer"
    assert result.metadata.score == 1.0
    assert result.metadata.reason == "exact_name"


def test_normalized_name_match_short_circuits() -> None:
    matcher = SubAgentDefinitionMatcher()
    result = matcher.match(_request("Research Analyst"), [_definition("research_analyst")])

    assert result is not None
    assert result.metadata.score == 0.95
    assert result.metadata.reason == "normalized_name"


def test_keyword_match_can_short_circuit_at_threshold() -> None:
    matcher = SubAgentDefinitionMatcher()
    result = matcher.match(
        _request("customer worker"),
        [
            _definition(
                "aum-customer-analyst",
                trigger_keywords=["AUM", "客户维护"],
            ),
        ],
    )

    assert result is not None
    assert result.definition.name == "aum-customer-analyst"
    assert result.metadata.score == 0.85


def test_low_score_falls_back_without_match() -> None:
    matcher = SubAgentDefinitionMatcher()
    result = matcher.match(
        _request("customer worker", "Summarize meeting notes."),
        [_definition("risk-reviewer", task_types=["risk"])],
    )

    assert result is None


def test_ties_use_stored_then_priority_then_name() -> None:
    matcher = SubAgentDefinitionMatcher()
    request = _request("customer worker")
    stored = _definition(
        "stored-a",
        source="stored",
        priority=20,
        trigger_keywords=["AUM", "客户维护"],
    )
    builtin = _definition(
        "builtin-a",
        source="builtin",
        priority=1,
        trigger_keywords=["AUM", "客户维护"],
    )

    result = matcher.match(request, [builtin, stored])

    assert result is not None
    assert result.definition.name == "stored-a"
```

- [ ] **Step 2: Run matcher tests and verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_definition_matcher.py -q
```

Expected: fail because matcher does not exist.

- [ ] **Step 3: Implement matcher**

Create `src/swe/app/subagents/matcher.py`:

```python
# -*- coding: utf-8 -*-
"""Deterministic SubAgent definition matching."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .models import (
    DefinitionMatchMetadata,
    SubAgentDefinition,
    SubAgentStartRequest,
)

SHORT_CIRCUIT_THRESHOLD = 0.85


@dataclass(frozen=True)
class DefinitionMatchResult:
    definition: SubAgentDefinition
    metadata: DefinitionMatchMetadata


def normalize_name(value: str) -> str:
    value = value.strip().casefold()
    return re.sub(r"[\s_-]+", "-", value)


class SubAgentDefinitionMatcher:
    """Rule-based matcher for stored and built-in SubAgent definitions."""

    def match(
        self,
        request: SubAgentStartRequest,
        candidates: list[SubAgentDefinition],
    ) -> DefinitionMatchResult | None:
        scored = [
            self._score(request, candidate)
            for candidate in candidates
            if candidate.enabled
        ]
        scored = [item for item in scored if item is not None]
        if not scored:
            return None
        scored.sort(key=self._sort_key)
        best = scored[0]
        if (best.metadata.score or 0) < SHORT_CIRCUIT_THRESHOLD:
            return None
        return best

    def _score(
        self,
        request: SubAgentStartRequest,
        candidate: SubAgentDefinition,
    ) -> DefinitionMatchResult | None:
        if request.name == candidate.name:
            return self._result(candidate, 1.0, "exact_name")
        if normalize_name(request.name) == normalize_name(candidate.name):
            return self._result(candidate, 0.95, "normalized_name")

        query = " ".join(
            [request.name, request.objective, request.background],
        ).casefold()
        keyword_hits = [
            keyword
            for keyword in candidate.trigger_keywords
            if keyword.strip().casefold() in query
        ]
        if keyword_hits:
            score = min(0.85, 0.65 + 0.1 * len(keyword_hits))
            return self._result(candidate, score, "trigger_keywords")

        task_hits = [
            task_type
            for task_type in candidate.task_types
            if task_type.strip().casefold() in query
        ]
        if task_hits:
            return self._result(candidate, 0.75, "task_types")

        description = candidate.description.strip().casefold()
        if description and description in query:
            return self._result(candidate, 0.70, "description")

        return None

    def _result(
        self,
        definition: SubAgentDefinition,
        score: float,
        reason: str,
    ) -> DefinitionMatchResult:
        return DefinitionMatchResult(
            definition=definition,
            metadata=DefinitionMatchMetadata(
                matched=True,
                definition_name=definition.name,
                definition_source=definition.source,
                score=score,
                reason=reason,
            ),
        )

    def _sort_key(self, result: DefinitionMatchResult) -> tuple:
        definition = result.definition
        source_rank = 0 if definition.source == "stored" else 1
        updated = definition.updated_at.timestamp()
        return (
            -(result.metadata.score or 0),
            source_rank,
            definition.priority,
            -updated,
            definition.name,
        )
```

- [ ] **Step 4: Wire matcher into definition service**

Modify `src/swe/app/subagents/definition_service.py`:

```python
from .matcher import DefinitionMatchResult, SubAgentDefinitionMatcher


class SubAgentDefinitionService:
    def __init__(..., matcher: SubAgentDefinitionMatcher | None = None):
        ...
        self._matcher = matcher or SubAgentDefinitionMatcher()

    def match_start_request(
        self,
        request: SubAgentStartRequest,
    ) -> DefinitionMatchResult | None:
        return self._matcher.match(request, self.list_available_definitions())
```

- [ ] **Step 5: Export matcher**

Modify `src/swe/app/subagents/__init__.py`:

```python
from .matcher import DefinitionMatchResult, SubAgentDefinitionMatcher, normalize_name
```

- [ ] **Step 6: Run matcher tests**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_definition_matcher.py tests/unit/subagents/test_definition_store_service.py -q
```

Expected: pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/swe/app/subagents/matcher.py src/swe/app/subagents/definition_service.py src/swe/app/subagents/__init__.py tests/unit/subagents/test_definition_matcher.py
git commit -m "feat(subagents): add deterministic definition matcher"
```

---

### Task 4: Tool Entrypoints

**Files:**
- Modify: `src/swe/agents/tools/subagent_background.py`
- Modify: `src/swe/agents/tools/__init__.py`
- Modify: `src/swe/agents/react_agent.py`
- Test: `tests/unit/subagents/test_background_tools.py`
- Test: `tests/unit/subagents/test_react_agent_and_guard_integration.py`

- [ ] **Step 1: Run GitNexus impact before editing tool registration symbols**

Use GitNexus impact on:
- `create_background_subagent_tools`
- `_register_background_subagent_tools`
- `_create_toolkit`

Expected: record risk. If helper symbols do not resolve, use `_create_toolkit` plus targeted tests.

- [ ] **Step 2: Write failing tests for compact start tool**

Update `tests/unit/subagents/test_background_tools.py`:

```python
@pytest.mark.asyncio
async def test_start_subagent_uses_compact_request_and_falls_back_run_scoped(tmp_path):
    captured = {}

    async def _start(**kwargs):
        captured.update(kwargs)
        return BackgroundSubAgentStartBlocked(limit=1)

    supervisor = SimpleNamespace(start=_start)
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={"tenant_id": "tenant-1", "agent_id": "agent-1"},
    )

    response = await tools["start_subagent"](
        name="aum-customer-analyst",
        instruction="Act as a customer strategy analyst.",
        objective="Analyze 1M AUM customer maintenance.",
        background="Need structured advice.",
    )
    payload = json.loads(response.content[0]["text"])

    assert payload["status"] == "blocked"
    assert captured["spec"].name == "aum-customer-analyst"
    assert captured["definition"].source == "run_scoped"
    assert captured["definition"].instruction == "Act as a customer strategy analyst."
    assert captured["start_request"].name == "aum-customer-analyst"
    assert captured["definition_match"].matched is False


@pytest.mark.asyncio
async def test_start_subagent_rejects_missing_instruction(tmp_path):
    tools = create_background_subagent_tools(
        supervisor=SimpleNamespace(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={"tenant_id": "tenant-1", "agent_id": "agent-1"},
    )

    response = await tools["start_subagent"](
        name="bad",
        instruction=" ",
        objective="Inspect",
    )
    payload = json.loads(response.content[0]["text"])

    assert payload["status"] == "failed"
    assert payload["reason"] == "invalid_request"
```

- [ ] **Step 3: Write failing test for registration tool visibility**

Update `tests/unit/subagents/test_react_agent_and_guard_integration.py`:

```python
def test_register_subagent_definition_requires_registration_intent(tmp_path: Path) -> None:
    normal = _bare_agent(
        tmp_path,
        request_context={
            "agent_role": "main",
            "current_user_text": "请用子代理分析这个模块",
        },
    )
    registration = _bare_agent(
        tmp_path,
        request_context={
            "agent_role": "main",
            "current_user_text": "注册一个可复用 SubAgent Definition",
        },
    )

    assert "start_subagent" in SWEAgent._create_toolkit(normal).tools
    assert "register_subagent_definition" not in SWEAgent._create_toolkit(normal).tools
    assert "register_subagent_definition" in SWEAgent._create_toolkit(registration).tools
```

- [ ] **Step 4: Run tool tests and verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_tools.py::test_start_subagent_uses_compact_request_and_falls_back_run_scoped tests/unit/subagents/test_background_tools.py::test_start_subagent_rejects_missing_instruction tests/unit/subagents/test_react_agent_and_guard_integration.py::test_register_subagent_definition_requires_registration_intent -q
```

Expected: fail because tools still use `agent_name` and no registration tool exists.

- [ ] **Step 5: Implement compact `start_subagent`**

Modify `src/swe/agents/tools/subagent_background.py`:

```python
async def start_subagent(
    name: str,
    instruction: str,
    objective: str,
    background: str = "",
) -> ToolResponse:
    try:
        start_request = SubAgentStartRequest.model_validate(
            {
                "name": name,
                "instruction": instruction,
                "objective": objective,
                "background": background,
            },
        )
    except Exception as exc:
        return _json_response(
            {
                "status": "failed",
                "reason": "invalid_request",
                "message": str(exc),
            },
        )

    service = _definition_service_for_tool(
        parent_agent_config=parent_agent_config,
        request_context=request_context,
    )
    match = service.match_start_request(start_request)
    if match is None:
        definition_match = DefinitionMatchMetadata(matched=False)
        definition = service.build_run_scoped_definition(
            start_request,
            owner_scope=f"run:{tool_scope.tenant_id}:{tool_scope.agent_id}",
        )
    else:
        definition_match = match.metadata
        definition = match.definition

    spec = DelegationSpec(
        parent_thread_id=str(request_context.get("session_id") or ""),
        name=start_request.name,
        objective=start_request.objective,
        background=start_request.background,
    )
    result = await supervisor.start(
        scope=tool_scope,
        spec=spec,
        parent_agent_config=parent_agent_config,
        workspace_dir=workspace_dir,
        parent_policy=_parent_policy_from_config(parent_agent_config),
        request_context=request_context,
        definition=definition,
        start_request=start_request,
        definition_match=definition_match,
    )
    return _json_response(_serialize_start_result(result))
```

Add helper:

```python
def _definition_service_for_tool(
    *,
    parent_agent_config: AgentProfileConfig,
    request_context: dict[str, Any],
) -> SubAgentDefinitionService:
    scope = build_background_subagent_scope(
        parent_agent_config=parent_agent_config,
        request_context=request_context,
    )
    store = SubAgentDefinitionStore(scope.run_store_dir.parent / "subagent_definitions")
    return SubAgentDefinitionService(
        store=store,
        builtin_registry=AgentRegistry([builtin_definition_provider()]),
        owner_scope=f"{scope.tenant_id}/{scope.agent_id}",
    )
```

- [ ] **Step 6: Implement `register_subagent_definition` tool**

In `create_background_subagent_tools`, add:

```python
async def register_subagent_definition(
    name: str,
    instruction: str,
    description: str,
    nickname: str | None = None,
    trigger_keywords: list[str] | None = None,
    task_types: list[str] | None = None,
    priority: int = 100,
    budget: dict[str, Any] | None = None,
    output_contract: str | None = None,
    enabled: bool = True,
) -> ToolResponse:
    try:
        request = SubAgentRegistrationRequest.model_validate(
            {
                "name": name,
                "instruction": instruction,
                "description": description,
                "nickname": nickname,
                "trigger_keywords": trigger_keywords or [],
                "task_types": task_types or [],
                "priority": priority,
                "budget": budget or {},
                "output_contract": output_contract or DEFAULT_OUTPUT_CONTRACT,
                "enabled": enabled,
            },
        )
        result = _definition_service_for_tool(
            parent_agent_config=parent_agent_config,
            request_context=request_context,
        ).register(request)
    except Exception as exc:
        result = {
            "status": "failed",
            "reason": "invalid_request",
            "message": str(exc),
        }
    return _json_response(result)
```

Return it from the tool dict:

```python
return {
    "start_subagent": start_subagent,
    "wait_subagent": wait_subagent,
    "get_subagent": get_subagent,
    "cancel_subagent": cancel_subagent,
    "register_subagent_definition": register_subagent_definition,
}
```

- [ ] **Step 7: Update tool registration intent**

In `src/swe/agents/react_agent.py`, register `register_subagent_definition` only when a new helper detects registration intent:

```python
def has_subagent_registration_intent(request_context: dict[str, Any]) -> bool:
    text = "\n".join(
        str(request_context.get(key) or "")
        for key in ("current_user_text", "user_message", "query", "prompt", "message_text")
    )
    return any(
        term in text
        for term in (
            "注册 SubAgent",
            "注册一个 SubAgent",
            "保存 SubAgent",
            "可复用 SubAgent",
            "register subagent",
            "stored subagent",
        )
    )
```

Then:

```python
if has_subagent_registration_intent(request_context):
    names.append("register_subagent_definition")
```

- [ ] **Step 8: Run tool tests**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_tools.py tests/unit/subagents/test_react_agent_and_guard_integration.py -q
```

Expected: pass.

- [ ] **Step 9: Commit Task 4**

```bash
git add src/swe/agents/tools/subagent_background.py src/swe/agents/tools/__init__.py src/swe/agents/react_agent.py tests/unit/subagents/test_background_tools.py tests/unit/subagents/test_react_agent_and_guard_integration.py
git commit -m "feat(subagents): add compact start and registration tools"
```

---

### Task 5: Runtime And Run Record

**Files:**
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/app/subagents/run_store.py`
- Modify: `src/swe/app/subagents/supervisor.py`
- Modify: `src/swe/app/subagents/worker.py`
- Modify: `src/swe/app/subagents/runtime.py`
- Test: `tests/unit/subagents/test_background_run_store.py`
- Test: `tests/unit/subagents/test_background_supervisor.py`
- Test: `tests/unit/subagents/test_runtime_and_delegation.py`
- Test: `tests/unit/subagents/test_background_worker.py`

- [ ] **Step 1: Write failing run record tests**

Update `tests/unit/subagents/test_background_run_store.py`:

```python
async def test_background_run_record_persists_start_request_match_and_nickname(tmp_path):
    store = PerRunSubAgentRunStore(tmp_path)
    start_request = SubAgentStartRequest.model_validate(
        {
            "name": "aum-customer-analyst",
            "instruction": "Act as an analyst.",
            "objective": "Analyze customers.",
        },
    )
    definition_match = DefinitionMatchMetadata(matched=False)
    definition = SubAgentDefinition.model_validate(
        {
            "name": "aum-customer-analyst",
            "source": "run_scoped",
            "owner_scope": "run:test",
            "description": "Analyze customers.",
            "instruction": "Act as an analyst.",
        },
    )

    record = await store.create(
        DelegationSpec(name="aum-customer-analyst", objective="Analyze customers."),
        definition,
        PermissionPolicy.readonly(),
        effective_budget=BudgetConfig(),
        start_request=start_request,
        definition_match=definition_match,
        nickname="研究员",
    )
    reloaded = await store.get(record.run_id)

    assert reloaded is not None
    assert reloaded.nickname == "研究员"
    assert reloaded.start_request.name == "aum-customer-analyst"
    assert reloaded.definition_match.matched is False
```

- [ ] **Step 2: Write failing runtime test for `instruction` and budget**

Update `tests/unit/subagents/test_runtime_and_delegation.py`:

```python
@pytest.mark.asyncio
async def test_runtime_uses_definition_instruction_and_no_max_tokens(monkeypatch, tmp_path):
    from swe.app.subagents import runtime as runtime_module

    _FakeSWEAgent.instances = []
    _FakeSWEAgent.replies = [
        Msg(
            "Friday",
            json.dumps(
                {
                    "task_id": "task-1",
                    "agent_run_id": "ignored",
                    "agent_name": "aum-customer-analyst",
                    "status": "completed",
                    "summary": "done",
                },
            ),
            "assistant",
        ),
    ]
    monkeypatch.setattr(runtime_module, "SWEAgent", _FakeSWEAgent)
    definition = SubAgentDefinition.model_validate(
        {
            "name": "aum-customer-analyst",
            "source": "run_scoped",
            "description": "Analyze customers.",
            "instruction": "Act as a customer strategy analyst.",
        },
    )
    store = InMemorySubAgentRunStore()
    record = await store.create(
        DelegationSpec(name="aum-customer-analyst", objective="Inspect"),
        definition,
        PermissionPolicy.readonly(),
    )

    await SubAgentRuntime(store=store).run(
        run=record,
        definition=definition,
        spec=record.spec,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        effective_policy=PermissionPolicy.readonly(),
    )

    prompt = _FakeSWEAgent.instances[0].kwargs["system_prompt_override"]
    assert "Act as a customer strategy analyst." in prompt
    assert "max_tokens" not in _FakeSWEAgent.instances[0].kwargs["request_context"]["subagent_budget"]
```

- [ ] **Step 3: Run run record/runtime tests and verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_run_store.py::test_background_run_record_persists_start_request_match_and_nickname tests/unit/subagents/test_runtime_and_delegation.py::test_runtime_uses_definition_instruction_and_no_max_tokens -q
```

Expected: fail because records do not have these fields and runtime reads `prompt.system`.

- [ ] **Step 4: Extend run record models**

Modify `BackgroundSubAgentRunRecord` and `SubAgentRunRecord` in `models.py`:

```python
nickname: str | None = None
start_request: SubAgentStartRequest | None = None
definition_match: DefinitionMatchMetadata = Field(default_factory=DefinitionMatchMetadata)
definition_source: DefinitionSource
```

Ensure `definition_name` remains the actual executed definition name, while `spec.name` remains the compact request name.

- [ ] **Step 5: Update stores to accept and persist metadata**

Modify `PerRunSubAgentRunStore.create(...)` and `InMemorySubAgentRunStore.create(...)` signatures:

```python
async def create(
    self,
    spec: DelegationSpec,
    definition: SubAgentDefinition,
    effective_policy: PermissionPolicy,
    *,
    effective_budget: BudgetConfig | None = None,
    start_request: SubAgentStartRequest | None = None,
    definition_match: DefinitionMatchMetadata | None = None,
    nickname: str | None = None,
) -> BackgroundSubAgentRunRecord:
```

Set:

```python
definition_name=definition.name
definition_source=definition.source
nickname=nickname
start_request=start_request
definition_match=definition_match or DefinitionMatchMetadata()
```

- [ ] **Step 6: Update supervisor start signature**

Modify `BackgroundSubAgentSupervisor.start(...)`:

```python
async def start(
    ...,
    definition: SubAgentDefinition | None = None,
    start_request: SubAgentStartRequest | None = None,
    definition_match: DefinitionMatchMetadata | None = None,
) -> BackgroundSubAgentRunRecord | BackgroundSubAgentStartBlocked:
```

Use provided definition; fallback to registry resolve only for test/helper paths that still call start directly:

```python
if definition is None:
    definition = self._registry.resolve(spec.name)
```

Assign nickname before store create:

```python
nickname = assign_subagent_nickname(definition.nickname)
record = await store.create(
    spec,
    definition,
    effective_policy,
    effective_budget=effective_budget,
    start_request=start_request,
    definition_match=definition_match,
    nickname=nickname,
)
```

- [ ] **Step 7: Update worker launch spec**

Modify `WorkerLaunchSpec` in `models.py` to include `start_request`, `definition_match`, and `nickname` if needed for worker-side record reconstruction.

Modify `worker.py` so `runtime_record = SubAgentRunRecord(...)` copies:

```python
nickname=record.nickname
start_request=record.start_request
definition_match=record.definition_match
definition_source=launch_spec.definition.source
```

- [ ] **Step 8: Update runtime to use `instruction` and remove `max_tokens`**

Modify `SubAgentRuntime._system_prompt(...)`:

```python
return "\n\n".join(
    [
        definition.instruction,
        "You must return valid AgentResult JSON.",
        ...
    ],
)
```

Modify `_effective_budget(...)`:

```python
return BudgetConfig(
    max_turns=min(definition_budget.max_turns, spec_budget.max_turns),
    max_tool_calls=min(definition_budget.max_tool_calls, spec_budget.max_tool_calls),
    timeout_ms=min(definition_budget.timeout_ms, spec_budget.timeout_ms),
)
```

Modify `_subagent_config(...)` to remove:

```python
config.running.max_input_length = min(config.running.max_input_length, budget.max_tokens)
```

- [ ] **Step 9: Update tests using `agent_name`**

Across `tests/unit/subagents`, replace `DelegationSpec(agent_name=...)` and assertions on `spec.agent_name` with `name`.

Run:

```bash
rg -n "agent_name|prompt\\.system|max_tokens" tests/unit/subagents src/swe/app/subagents
```

Expected after edits: no production references to `agent_name`, `prompt.system`, or SubAgent `max_tokens`; test references only when asserting legacy fields are rejected.

- [ ] **Step 10: Run runtime/run store tests**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_run_store.py tests/unit/subagents/test_background_supervisor.py tests/unit/subagents/test_runtime_and_delegation.py tests/unit/subagents/test_background_worker.py -q
```

Expected: pass.

- [ ] **Step 11: Commit Task 5**

```bash
git add src/swe/app/subagents/models.py src/swe/app/subagents/run_store.py src/swe/app/subagents/supervisor.py src/swe/app/subagents/worker.py src/swe/app/subagents/runtime.py tests/unit/subagents/test_background_run_store.py tests/unit/subagents/test_background_supervisor.py tests/unit/subagents/test_runtime_and_delegation.py tests/unit/subagents/test_background_worker.py
git commit -m "refactor(subagents): persist run-scoped start metadata"
```

---

### Task 6: Monitor Response

**Files:**
- Modify: `src/swe/agents/tools/subagent_background.py`
- Modify: `src/swe/app/subagents/monitor.py`
- Modify: `src/swe/app/routers/subagents.py`
- Test: `tests/unit/subagents/test_background_tools.py`
- Test: `tests/unit/subagents/test_monitor_api.py`

- [ ] **Step 1: Write failing compact response tests**

Update `tests/unit/subagents/test_background_tools.py`:

```python
@pytest.mark.asyncio
async def test_start_response_includes_nickname_and_match_metadata(tmp_path):
    definition = AgentRegistry([builtin_definition_provider()]).resolve("risk-reviewer")
    record = await PerRunSubAgentRunStore(tmp_path / "runs").create(
        DelegationSpec(name="risk-reviewer", objective="Inspect"),
        definition,
        PermissionPolicy.readonly(),
        nickname="风险观察员",
        definition_match=DefinitionMatchMetadata(
            matched=True,
            definition_name="risk-reviewer",
            definition_source="builtin",
            score=1.0,
            reason="exact_name",
        ),
    )
    supervisor = SimpleNamespace(start=_AsyncReturn(record))
    tools = create_background_subagent_tools(
        supervisor=supervisor,
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={"tenant_id": "tenant-1", "agent_id": "agent-1"},
    )

    response = await tools["start_subagent"](
        name="risk-reviewer",
        instruction="Act as a risk reviewer.",
        objective="Inspect risks.",
    )
    payload = json.loads(response.content[0]["text"])

    assert payload["nickname"] == "风险观察员"
    assert payload["definition_match"]["matched"] is True
    assert payload["definition_match"]["definition_name"] == "risk-reviewer"
```

- [ ] **Step 2: Write failing monitor API test**

Update `tests/unit/subagents/test_monitor_api.py`:

```python
def test_monitor_snapshot_includes_nickname_and_definition_match(
    client_store_fixture,
) -> None:
    client, store, _supervisor = client_store_fixture
    record = _background_record(
        run_id="subagent-running",
        chat_id="chat-1",
        nickname="研究员",
        definition_match={
            "matched": False,
        },
    )
    store.write(record)

    response = client.get("/subagents/runs", params={"chat_id": "chat-1"})

    assert response.status_code == 200
    run = response.json()["runs"][0]
    assert run["nickname"] == "研究员"
    assert run["definition_match"]["matched"] is False
```

Use the actual fixture/helper names present in `tests/unit/subagents/test_monitor_api.py`; keep the assertions identical.

- [ ] **Step 3: Run monitor/response tests and verify RED**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_tools.py::test_start_response_includes_nickname_and_match_metadata tests/unit/subagents/test_monitor_api.py::test_monitor_snapshot_includes_nickname_and_definition_match -q
```

Expected: fail because serializers do not include the new fields.

- [ ] **Step 4: Update tool serializers**

Modify `_compact_record(...)` in `src/swe/agents/tools/subagent_background.py`:

```python
payload = {
    "run_id": record.run_id,
    "status": record.status,
    "name": record.spec.name,
    "nickname": getattr(record, "nickname", None),
    "objective": record.spec.objective,
    "definition_name": record.definition_name,
    "definition_source": record.definition_source,
    "definition_match": _dump_json_value(record.definition_match),
    ...
}
```

Remove output key `agent_name`; new consumers use `name`.

- [ ] **Step 5: Update monitor snapshot models**

Modify `src/swe/app/subagents/monitor.py`:

```python
class SubAgentRunSnapshotItem(BaseModel):
    run_id: str
    status: str
    name: str
    nickname: str | None = None
    objective: str
    definition_name: str
    definition_source: str
    definition_match: dict[str, Any] = Field(default_factory=dict)
    ...
```

Update `_to_item(...)`:

```python
return SubAgentRunSnapshotItem(
    run_id=record.run_id,
    status=record.status,
    name=record.spec.name,
    nickname=record.nickname,
    objective=record.spec.objective,
    definition_name=record.definition_name,
    definition_source=record.definition_source,
    definition_match=record.definition_match.model_dump(mode="json"),
    ...
)
```

- [ ] **Step 6: Update router response tests and frontend contract if present**

Search for snapshot field assumptions:

```bash
rg -n "agent_name|definition_match|nickname" tests/unit/subagents console/src/pages/Chat src/swe/app/routers/subagents.py src/swe/app/subagents/monitor.py
```

Replace `agent_name` display assumptions with `name` or `nickname`:
- User-facing display should prefer `nickname`.
- Debug/detail display may show `name`.

- [ ] **Step 7: Run monitor and tool tests**

Run:

```bash
venv/bin/python -m pytest tests/unit/subagents/test_background_tools.py tests/unit/subagents/test_monitor_api.py -q
```

Expected: pass.

- [ ] **Step 8: Commit Task 6**

```bash
git add src/swe/agents/tools/subagent_background.py src/swe/app/subagents/monitor.py src/swe/app/routers/subagents.py tests/unit/subagents/test_background_tools.py tests/unit/subagents/test_monitor_api.py
git commit -m "feat(subagents): expose run nickname and match metadata"
```

---

## Final Verification

- [ ] **Run all SubAgent unit tests**

```bash
venv/bin/python -m pytest tests/unit/subagents -q
```

Expected: all tests pass.

- [ ] **Run focused Agent toolkit tests**

```bash
venv/bin/python -m pytest tests/unit/subagents/test_react_agent_and_guard_integration.py -q
```

Expected: all tests pass, with `start_subagent` available for SubAgent intent and `register_subagent_definition` hidden unless registration intent is present.

- [ ] **Search for legacy fields**

```bash
rg -n "agent_name|system_prompt|prompt\\.system|max_tokens" src/swe/app/subagents src/swe/agents/tools/subagent_background.py tests/unit/subagents
```

Expected:
- No production references to old SubAgent fields.
- Any remaining test references are only explicit rejection tests.

- [ ] **Run GitNexus detect changes**

Use:

```text
mcp__gitnexus.detect_changes({repo: "CoPaw", scope: "unstaged"})
```

Expected: affected scope limited to SubAgent model/store/service/matcher/runtime/tool/monitor paths. If unrelated workspace changes are present, list them separately and do not revert them.

- [ ] **Run broader regression if time allows**

```bash
venv/bin/python -m pytest tests/unit/agents tests/unit/subagents -q
```

Expected: all tests pass or only unrelated pre-existing failures are documented with exact failure names.

---

## Self-Review

**Spec coverage:**
- Model migration: Task 1.
- Store/service: Task 2.
- Matcher: Task 3.
- Tool entrypoints: Task 4.
- Runtime/run record: Task 5.
- Monitor response: Task 6.
- ADR and glossary updates are already present in `CONTEXT.md` and `docs/adr/0010-run-scoped-subagent-definitions-and-routing.md`.

**Placeholder scan:** This plan intentionally avoids placeholder markers. Each task includes concrete files, tests, commands, and implementation shapes.

**Type consistency:** The canonical fields are `name`, `instruction`, `output_contract`, `nickname`, `trigger_keywords`, `task_types`, `priority`, `start_request`, and `definition_match`. The old fields `agent_name`, `system_prompt`, and `prompt.system` are rejected rather than supported.
