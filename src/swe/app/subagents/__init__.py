# -*- coding: utf-8 -*-
"""SubAgent runtime primitives for bounded internal delegation."""

from .builtins import builtin_definition_provider
from .definition_service import SubAgentDefinitionService
from .definition_store import DefinitionUpsertResult, SubAgentDefinitionStore
from .manager import DelegationManager
from .matcher import (
    DefinitionMatchResult,
    SubAgentDefinitionMatcher,
    normalize_name,
)
from .models import (
    AgentResult,
    BackgroundRunStatus,
    BackgroundSubAgentRunRecord,
    DelegationSpec,
    DefinitionMatchMetadata,
    DefinitionValidationError,
    PermissionPolicy,
    SubAgentDefinition,
    SubAgentRegistrationRequest,
    SubAgentRunRecord,
    SubAgentStartRequest,
    TERMINAL_BACKGROUND_RUN_STATUSES,
    WorkerLaunchSpec,
    WorkerProcessInfo,
    ToolAuthorizationDecision,
    SkillOwnedDefinitionMetadata,
    SkillOwnedModelReference,
    SkillOwnedToolConfig,
)
from .skill_definitions import (
    SubAgentDefinitionCatalog,
    SkillDefinitionLoadError,
    SkillDefinitionLoadResult,
    build_definition_catalog,
    load_skill_owned_definitions,
)
from .permissions import compose_effective_policy, validate_tool_call
from .nicknames import assign_subagent_nickname
from .registry import (
    AgentRegistry,
    InMemoryDefinitionProvider,
    SubAgentDefinitionProvider,
)
from .run_store import (
    InMemorySubAgentRunStore,
    LocalJsonSubAgentRunStore,
    PerRunSubAgentRunStore,
    SubAgentRunStore,
)
from .supervisor import (
    BackgroundSubAgentNotManageable,
    BackgroundSubAgentScope,
    BackgroundSubAgentStartBlocked,
    BackgroundSubAgentSupervisor,
    BackgroundSubAgentWaitSnapshot,
)
from .runtime import SubAgentRuntime

__all__ = [
    "AgentRegistry",
    "AgentResult",
    "BackgroundRunStatus",
    "BackgroundSubAgentNotManageable",
    "BackgroundSubAgentRunRecord",
    "BackgroundSubAgentScope",
    "BackgroundSubAgentStartBlocked",
    "BackgroundSubAgentSupervisor",
    "BackgroundSubAgentWaitSnapshot",
    "DelegationManager",
    "DelegationSpec",
    "DefinitionMatchResult",
    "DefinitionMatchMetadata",
    "DefinitionUpsertResult",
    "DefinitionValidationError",
    "InMemoryDefinitionProvider",
    "InMemorySubAgentRunStore",
    "LocalJsonSubAgentRunStore",
    "PerRunSubAgentRunStore",
    "PermissionPolicy",
    "SubAgentDefinition",
    "SubAgentDefinitionMatcher",
    "SubAgentDefinitionService",
    "SubAgentDefinitionStore",
    "SubAgentDefinitionProvider",
    "SubAgentRegistrationRequest",
    "SubAgentRunRecord",
    "SubAgentRuntime",
    "SubAgentRunStore",
    "SubAgentStartRequest",
    "TERMINAL_BACKGROUND_RUN_STATUSES",
    "ToolAuthorizationDecision",
    "SkillDefinitionLoadError",
    "SkillDefinitionLoadResult",
    "SubAgentDefinitionCatalog",
    "SkillOwnedDefinitionMetadata",
    "SkillOwnedModelReference",
    "SkillOwnedToolConfig",
    "WorkerLaunchSpec",
    "WorkerProcessInfo",
    "assign_subagent_nickname",
    "builtin_definition_provider",
    "compose_effective_policy",
    "normalize_name",
    "validate_tool_call",
    "load_skill_owned_definitions",
    "build_definition_catalog",
]
