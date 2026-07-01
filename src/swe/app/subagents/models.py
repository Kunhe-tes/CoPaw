# -*- coding: utf-8 -*-
"""Pydantic models for SubAgent definitions, specs, results, and runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

DefinitionSource = Literal["builtin", "user"]
AgentResultStatus = Literal[
    "completed",
    "partial",
    "blocked",
    "failed",
    "cancelled",
]
RunStatus = Literal[
    "queued",
    "running",
    "completed",
    "partial",
    "blocked",
    "failed",
    "cancelled",
]

KNOWN_BUILTIN_TOOLS = frozenset(
    {
        "execute_shell_command",
        "read_file",
        "write_file",
        "edit_file",
        "grep_search",
        "glob_search",
        "get_current_time",
        "set_user_timezone",
        "get_token_usage",
        "copy_file_to_static",
        "update_task_progress",
    },
)
MVP_READONLY_TOOLS = frozenset(
    {
        "execute_shell_command",
        "read_file",
        "grep_search",
        "glob_search",
        "get_current_time",
    },
)
MUTATING_TOOLS = frozenset(
    {
        "write_file",
        "edit_file",
        "set_user_timezone",
        "get_token_usage",
        "copy_file_to_static",
        "update_task_progress",
    },
)
READONLY_ALLOWED_COMMANDS = (
    "pwd",
    "ls",
    "rg",
    "grep",
    "sed",
    "git status",
    "git diff",
    "git grep",
    "git log",
    "git show",
)
READONLY_ALLOWED_COMMAND_SET = frozenset(READONLY_ALLOWED_COMMANDS)


class DefinitionValidationError(ValueError):
    """Structured validation error for unsafe SubAgent definitions."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ToolSet(BaseModel):
    """Allowed and denied built-in tool names for a SubAgent."""

    allow: list[str] = Field(
        default_factory=lambda: sorted(MVP_READONLY_TOOLS),
    )
    deny: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)


class ShellPolicy(BaseModel):
    """Shell authorization settings for readonly SubAgents."""

    enabled: bool = True
    strategy: Literal["deny_all", "allowlist"] = "allowlist"
    allowed_commands: list[str] = Field(
        default_factory=lambda: list(READONLY_ALLOWED_COMMANDS),
    )
    denied_patterns: list[str] = Field(
        default_factory=lambda: [
            ">",
            ">>",
            "| tee",
            " rm ",
            "rm -",
            "mv ",
            "cp ",
            "git checkout",
            "git reset",
            "git clean",
            "pytest",
            "npm test",
            "coverage",
            "snapshot",
            "black",
            "ruff --fix",
            "migrate",
            "deploy",
        ],
    )


class MutationPolicy(BaseModel):
    """Mutation switches that must remain disabled for readonly MVP runs."""

    allow_file_write: bool = False
    allow_patch: bool = False
    allow_delete: bool = False
    allow_format_write: bool = False
    allow_migration: bool = False
    allow_deploy: bool = False


class PermissionTools(BaseModel):
    """Tool-level allow/deny sets."""

    allow: list[str] = Field(
        default_factory=lambda: sorted(MVP_READONLY_TOOLS),
    )
    deny: list[str] = Field(default_factory=list)
    ask: list[str] = Field(default_factory=list)


class PermissionPolicy(BaseModel):
    """Effective or source permission policy for SubAgent execution."""

    mode: Literal["readonly"] = "readonly"
    tools: PermissionTools = Field(default_factory=PermissionTools)
    shell: ShellPolicy = Field(default_factory=ShellPolicy)
    mutation: MutationPolicy = Field(default_factory=MutationPolicy)
    network_enabled: bool = False

    @classmethod
    def readonly(
        cls,
        *,
        allow_tools: list[str] | None = None,
        deny_tools: list[str] | None = None,
    ) -> "PermissionPolicy":
        """Create a readonly policy with optional allow/deny overrides."""
        return cls(
            tools=PermissionTools(
                allow=list(allow_tools or sorted(MVP_READONLY_TOOLS)),
                deny=list(deny_tools or []),
            ),
        )


class ModelRouting(BaseModel):
    """Model routing metadata; MVP only supports inheritance."""

    behavior: Literal["inherit"] = "inherit"


class PromptContract(BaseModel):
    """Definition prompt and output contract."""

    system: str
    output_contract: str = "Return valid AgentResult JSON only."


class IsolationConfig(BaseModel):
    """SubAgent context/workspace/memory isolation settings."""

    context: Literal["fresh", "fork"] = "fresh"
    workspace: Literal["shared", "sandbox", "worktree"] = "shared"
    memory: Literal["none", "session", "project", "user"] = "none"
    skills_enabled: bool = False
    mcp_enabled: bool = False


class BudgetConfig(BaseModel):
    """MVP execution budgets for a SubAgent run."""

    max_turns: int = 6
    max_tool_calls: int = 30
    max_tokens: int = 12000
    timeout_ms: int = 120000


class LifecycleConfig(BaseModel):
    """SubAgent lifecycle capabilities."""

    resumable: bool = False
    cancellable: bool = True
    allow_nested_delegation: bool = False


class RoutingMetadata(BaseModel):
    """Task routing hints for future planner use."""

    task_types: list[str] = Field(default_factory=list)
    trigger_keywords: list[str] = Field(default_factory=list)
    priority: int = 100


class SubAgentDefinition(BaseModel):
    """A named, versioned definition for a bounded SubAgent worker."""

    name: str
    version: str = "1.0.0"
    schema_version: str = "subagent.definition.v1"
    source: DefinitionSource = "builtin"
    owner_scope: str = "builtin"
    enabled: bool = True
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)
    created_by: str | None = None
    description: str
    role: str = "researcher"
    model: ModelRouting = Field(default_factory=ModelRouting)
    prompt: PromptContract
    tools: ToolSet = Field(default_factory=ToolSet)
    permission: PermissionPolicy = Field(default_factory=PermissionPolicy)
    isolation: IsolationConfig = Field(default_factory=IsolationConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    routing: RoutingMetadata = Field(default_factory=RoutingMetadata)
    lifecycle: LifecycleConfig = Field(default_factory=LifecycleConfig)

    @classmethod
    def model_validate(cls, obj: Any, *args: Any, **kwargs: Any):
        instance = super().model_validate(obj, *args, **kwargs)
        errors = instance.validation_errors()
        if errors:
            raise DefinitionValidationError("; ".join(errors))
        return instance

    def validation_errors(self) -> list[str]:
        """Return MVP safety validation errors for this definition."""
        errors: list[str] = []
        if not self.prompt.system.strip():
            errors.append("missing prompt")
        if self.lifecycle.allow_nested_delegation:
            errors.append("nested delegation is unsupported")
        if self.isolation.context != "fresh":
            errors.append("unsupported context isolation")
        if self.isolation.workspace != "shared":
            errors.append("unsupported workspace isolation")
        if self.isolation.memory != "none":
            errors.append("persistent memory is unsupported")
        if self.isolation.skills_enabled:
            errors.append("workspace skills are unsupported")
        if self.isolation.mcp_enabled or self.tools.mcp_servers:
            errors.append("MCP tools are unsupported")
        if self.model.behavior != "inherit":
            errors.append("custom model routing is unsupported")
        for tool in self.tools.allow + self.tools.deny:
            if tool.startswith("mcp:"):
                errors.append("MCP tools are unsupported")
            elif tool not in KNOWN_BUILTIN_TOOLS:
                errors.append(f"unknown built-in tool: {tool}")
        mutating = sorted(set(self.tools.allow) & MUTATING_TOOLS)
        if mutating:
            errors.append(
                f"mutating tool is unsupported: {', '.join(mutating)}",
            )
        permission_mutating = sorted(
            set(self.permission.tools.allow) & MUTATING_TOOLS,
        )
        if permission_mutating:
            errors.append(
                "permission mutating tool is unsupported: "
                + ", ".join(permission_mutating),
            )
        permission_tools = (
            self.permission.tools.allow
            + self.permission.tools.deny
            + self.permission.tools.ask
        )
        for tool in permission_tools:
            if tool not in KNOWN_BUILTIN_TOOLS and not tool.startswith("mcp:"):
                errors.append(f"unknown built-in tool: {tool}")
        permission_mcp = sorted(
            tool for tool in permission_tools if tool.startswith("mcp:")
        )
        if permission_mcp:
            errors.append("permission MCP tools are unsupported")
        unsupported_permission_commands = sorted(
            set(self.permission.shell.allowed_commands)
            - READONLY_ALLOWED_COMMAND_SET,
        )
        if unsupported_permission_commands:
            errors.append(
                "permission shell allowed_commands widen readonly scope: "
                + ", ".join(unsupported_permission_commands),
            )
        return errors


class ModeContext(BaseModel):
    """Parent-mode metadata for a delegated task."""

    parent_mode: Literal["normal", "plan", "execute", "goal"] = "normal"
    goal_id: str | None = None
    plan_id: str | None = None


class ScopeConfig(BaseModel):
    """Path and symbol scope for a delegated task."""

    include_paths: list[str] = Field(default_factory=list)
    exclude_paths: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)


class EvidenceRequirement(BaseModel):
    """Evidence requested by the parent agent."""

    type: Literal["file", "command", "diff", "test", "log", "artifact"]
    required: bool = True
    description: str


class ExpectedOutput(BaseModel):
    """Delegated output contract metadata."""

    format: Literal["json"] = "json"
    schema_name: Literal["AgentResult"] = "AgentResult"
    required_sections: list[str] = Field(
        default_factory=lambda: [
            "summary",
            "findings",
            "relevant_files",
            "risks",
            "recommendations",
            "open_questions",
        ],
    )


class ReturnPolicy(BaseModel):
    """Controls how much raw SubAgent material can return to the parent."""

    include_raw_logs: bool = False
    include_file_snippets: bool = False
    max_summary_tokens: int = 2000


class DelegationSpec(BaseModel):
    """Structured task sent from a main agent to a named SubAgent."""

    task_id: str = Field(default_factory=lambda: f"task-{uuid4().hex[:12]}")
    parent_thread_id: str = ""
    agent_name: str
    objective: str
    background: str = ""
    mode_context: ModeContext = Field(default_factory=ModeContext)
    scope: ScopeConfig = Field(default_factory=ScopeConfig)
    constraints: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    evidence_requirements: list[EvidenceRequirement] = Field(
        default_factory=list,
    )
    expected_output: ExpectedOutput = Field(default_factory=ExpectedOutput)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    return_policy: ReturnPolicy = Field(default_factory=ReturnPolicy)


class LineRange(BaseModel):
    """Line range for evidence references."""

    start: int
    end: int


class EvidenceRef(BaseModel):
    """Reference to evidence gathered by a SubAgent."""

    type: Literal[
        "file",
        "symbol",
        "command",
        "diff",
        "test",
        "log",
        "artifact",
    ]
    ref: str
    detail: str = ""
    line_range: LineRange | None = None
    command_exit_code: int | None = None


class Finding(BaseModel):
    """A claim and its supporting evidence."""

    claim: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"


class RelevantFile(BaseModel):
    """File surfaced by a SubAgent."""

    path: str
    reason: str = ""
    importance: Literal["high", "medium", "low"] = "medium"


class Risk(BaseModel):
    """Risk surfaced by a SubAgent."""

    risk: str
    reason: str = ""
    mitigation: str | None = None
    severity: Literal["critical", "high", "medium", "low"] = "medium"


class Recommendation(BaseModel):
    """Recommended parent-agent action."""

    recommendation: str
    rationale: str = ""
    priority: Literal["must", "should", "could"] = "should"


class Metrics(BaseModel):
    """Runtime metrics for a SubAgent result."""

    turns_used: int = 0
    tool_calls_used: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    elapsed_ms: int = 0


class ArtifactRef(BaseModel):
    """Reference to an artifact produced by a SubAgent."""

    type: str = "artifact"
    ref: str
    description: str = ""


class AgentError(BaseModel):
    """Structured SubAgent error."""

    code: str
    message: str
    recoverable: bool = False


class AgentResult(BaseModel):
    """Compact structured output returned from a SubAgent to the caller."""

    task_id: str
    agent_run_id: str
    agent_name: str
    status: AgentResultStatus
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    relevant_files: list[RelevantFile] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    suggested_next_steps: list[str] = Field(default_factory=list)
    metrics: Metrics = Field(default_factory=Metrics)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    errors: list[AgentError] = Field(default_factory=list)


class ToolAuthorizationDecision(BaseModel):
    """Decision for a single tool call under a SubAgent policy."""

    allowed: bool
    reason: str = ""


class SubAgentRunRecord(BaseModel):
    """Persisted lifecycle record for one delegated SubAgent run."""

    run_id: str = Field(default_factory=lambda: f"subagent-{uuid4().hex[:12]}")
    status: RunStatus = "queued"
    spec: DelegationSpec
    definition_name: str
    definition_version: str
    definition_source: DefinitionSource
    owner_scope: str
    effective_policy: PermissionPolicy
    result: AgentResult | None = None
    errors: list[AgentError] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now_utc)
    started_at: datetime | None = None
    finished_at: datetime | None = None
