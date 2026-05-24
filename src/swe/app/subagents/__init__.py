# -*- coding: utf-8 -*-
"""SubAgent runtime primitives for bounded internal delegation."""

from .builtins import builtin_definition_provider
from .manager import DelegationManager
from .models import (
    AgentResult,
    DelegationSpec,
    DefinitionValidationError,
    EvidenceRef,
    PermissionPolicy,
    SubAgentDefinition,
    SubAgentRunRecord,
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
    SubAgentRunStore,
)
from .runtime import SubAgentRuntime

__all__ = [
    "AgentRegistry",
    "AgentResult",
    "DelegationManager",
    "DelegationSpec",
    "DefinitionValidationError",
    "EvidenceRef",
    "InMemoryDefinitionProvider",
    "InMemorySubAgentRunStore",
    "LocalJsonSubAgentRunStore",
    "PermissionPolicy",
    "SubAgentDefinition",
    "SubAgentDefinitionStore",
    "SubAgentDefinitionProvider",
    "SubAgentRunRecord",
    "SubAgentRuntime",
    "SubAgentRunStore",
    "ToolAuthorizationDecision",
    "builtin_definition_provider",
    "compose_effective_policy",
    "validate_tool_call",
]
