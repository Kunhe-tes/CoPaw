# -*- coding: utf-8 -*-
"""SubAgent runtime primitives for bounded internal delegation."""

from .builtins import builtin_definition_provider
from .definition_service import SubAgentDefinitionService
from .definition_store import DefinitionUpsertResult, SubAgentDefinitionStore
from .manager import DelegationManager
from .models import (
    AgentResult,
    BackgroundRunStatus,
    BackgroundSubAgentRunRecord,
    DelegationSpec,
    DefinitionMatchMetadata,
    DefinitionValidationError,
    EvidenceRef,
    PermissionPolicy,
    SubAgentDefinition,
    SubAgentRegistrationRequest,
    SubAgentRunRecord,
    SubAgentStartRequest,
    TERMINAL_BACKGROUND_RUN_STATUSES,
    WorkerLaunchSpec,
    WorkerProcessInfo,
    ToolAuthorizationDecision,
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
    "DefinitionMatchMetadata",
    "DefinitionUpsertResult",
    "DefinitionValidationError",
    "EvidenceRef",
    "InMemoryDefinitionProvider",
    "InMemorySubAgentRunStore",
    "LocalJsonSubAgentRunStore",
    "PerRunSubAgentRunStore",
    "PermissionPolicy",
    "SubAgentDefinition",
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
    "WorkerLaunchSpec",
    "WorkerProcessInfo",
    "assign_subagent_nickname",
    "builtin_definition_provider",
    "compose_effective_policy",
    "validate_tool_call",
]
