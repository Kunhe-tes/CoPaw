# -*- coding: utf-8 -*-
"""SubAgent runtime primitives for bounded internal delegation."""

from .builtins import builtin_definition_provider
from .manager import DelegationManager
from .models import (
    AgentResult,
    BackgroundRunStatus,
    BackgroundSubAgentRunRecord,
    DelegationSpec,
    DefinitionValidationError,
    EvidenceRef,
    PermissionPolicy,
    SubAgentDefinition,
    SubAgentRunRecord,
    TERMINAL_BACKGROUND_RUN_STATUSES,
    WorkerLaunchSpec,
    WorkerProcessInfo,
    ToolAuthorizationDecision,
)
from .permissions import compose_effective_policy, validate_tool_call
from .registry import (
    AgentRegistry,
    InMemoryDefinitionProvider,
    SubAgentDefinitionStore,
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
    "DefinitionValidationError",
    "EvidenceRef",
    "InMemoryDefinitionProvider",
    "InMemorySubAgentRunStore",
    "LocalJsonSubAgentRunStore",
    "PerRunSubAgentRunStore",
    "PermissionPolicy",
    "SubAgentDefinition",
    "SubAgentDefinitionStore",
    "SubAgentDefinitionProvider",
    "SubAgentRunRecord",
    "SubAgentRuntime",
    "SubAgentRunStore",
    "TERMINAL_BACKGROUND_RUN_STATUSES",
    "ToolAuthorizationDecision",
    "WorkerLaunchSpec",
    "WorkerProcessInfo",
    "builtin_definition_provider",
    "compose_effective_policy",
    "validate_tool_call",
]
