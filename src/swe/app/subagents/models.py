# -*- coding: utf-8 -*-
"""Pydantic models for SubAgent definitions, specs, results, and runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

DefinitionSource = Literal["builtin", "stored", "run_scoped"]
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
BackgroundRunStatus = Literal[
    "pending",
    "running",
    "paused",
    "completed",
    "failed",
    "cancelled",
    "expired",
]
TERMINAL_BACKGROUND_RUN_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "expired"},
)
SAFE_WORKER_REQUEST_CONTEXT_KEYS = frozenset(
    {
        "session_id",
        "chat_id",
        "turn_id",
        "user_id",
        "channel",
        "source_id",
        "trace_id",
        "tenant_id",
        "scope_id",
        "agent_id",
    },
)
SECRET_LIKE_FIELD_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "credential",
    "access_token",
    "refresh_token",
)
MAX_MATCHING_LIST_ITEMS = 20
MAX_MATCHING_LIST_ITEM_CHARS = 64
START_OBJECTIVE_MAX_BYTES = 4096
START_BACKGROUND_MAX_BYTES = 16384


def _drop_secret_like_fields(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if any(
                fragment in normalized
                for fragment in SECRET_LIKE_FIELD_FRAGMENTS
            ):
                continue
            safe[key] = _drop_secret_like_fields(item)
        return safe
    if isinstance(value, list):
        return [_drop_secret_like_fields(item) for item in value]
    return value


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


def _validate_limited_string_list(
    values: list[str],
    *,
    field_name: str,
    max_items: int = MAX_MATCHING_LIST_ITEMS,
) -> list[str]:
    if len(values) > max_items:
        raise ValueError(f"{field_name} has too many items")
    cleaned: list[str] = []
    for value in values:
        item = value.strip()
        if not item:
            raise ValueError(f"{field_name} contains an empty item")
        if len(item) > MAX_MATCHING_LIST_ITEM_CHARS:
            raise ValueError(f"{field_name} item exceeds 64 characters")
        cleaned.append(item)
    return cleaned


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


class IsolationConfig(BaseModel):
    """SubAgent context/workspace/memory isolation settings."""

    context: Literal["fresh", "fork"] = "fresh"
    workspace: Literal["shared", "sandbox", "worktree"] = "shared"
    memory: Literal["none", "session", "project", "user"] = "none"
    skills_enabled: bool = False
    mcp_enabled: bool = False


class BudgetConfig(BaseModel):
    """MVP execution budgets for a SubAgent run."""

    model_config = ConfigDict(extra="forbid")

    max_turns: int = 6
    max_tool_calls: int = 30
    timeout_ms: int = 120000


class LifecycleConfig(BaseModel):
    """SubAgent lifecycle capabilities."""

    resumable: bool = False
    cancellable: bool = True
    allow_nested_delegation: bool = False


class SubAgentDefinition(BaseModel):
    """A named, versioned definition for a bounded SubAgent worker."""

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

    @field_validator("task_types", "trigger_keywords")
    @classmethod
    def _validate_matching_lists(
        cls,
        value: list[str],
        info: Any,
    ) -> list[str]:
        return _validate_limited_string_list(
            value,
            field_name=info.field_name,
        )

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
        if not self.instruction.strip():
            errors.append("missing instruction")
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

    model_config = ConfigDict(extra="forbid")

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
    evidence_requirements: list[EvidenceRequirement] = Field(
        default_factory=list,
    )
    expected_output: ExpectedOutput = Field(default_factory=ExpectedOutput)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    return_policy: ReturnPolicy = Field(default_factory=ReturnPolicy)

    @field_validator("name", "objective", mode="after")
    @classmethod
    def _non_empty_required_string(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must be non-empty")
        return value


class SubAgentStartRequest(BaseModel):
    """Compact request used by the main agent to start one SubAgent run."""

    model_config = ConfigDict(extra="forbid")

    name: str
    instruction: str
    objective: str
    background: str = ""

    @field_validator("name", "instruction", "objective", mode="after")
    @classmethod
    def _non_empty_required_string(cls, value: str) -> str:
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

    @field_validator("objective")
    @classmethod
    def _objective_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > START_OBJECTIVE_MAX_BYTES:
            raise ValueError("objective exceeds 4096 bytes")
        return value

    @field_validator("background")
    @classmethod
    def _background_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > START_BACKGROUND_MAX_BYTES:
            raise ValueError("background exceeds 16384 bytes")
        return value


class SubAgentRegistrationRequest(BaseModel):
    """Full request used by management tools to register stored definitions."""

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

    @field_validator("name", "instruction", "description", mode="after")
    @classmethod
    def _non_empty_required_string(cls, value: str) -> str:
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

    @field_validator("task_types", "trigger_keywords")
    @classmethod
    def _validate_matching_lists(
        cls,
        value: list[str],
        info: Any,
    ) -> list[str]:
        return _validate_limited_string_list(
            value,
            field_name=info.field_name,
        )


class DefinitionMatchMetadata(BaseModel):
    """Metadata describing deterministic definition matching for a run."""

    matched: bool = False
    definition_name: str | None = None
    definition_source: DefinitionSource | None = None
    score: float | None = None
    reason: str | None = None


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
    nickname: str | None = None
    start_request: SubAgentStartRequest | None = None
    definition_match: DefinitionMatchMetadata = Field(
        default_factory=DefinitionMatchMetadata,
    )
    result: AgentResult | None = None
    errors: list[AgentError] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now_utc)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class WorkerProcessInfo(BaseModel):
    """Observable subprocess metadata for a Background SubAgent Run."""

    pid: int
    started_at: datetime = Field(default_factory=_now_utc)
    exit_code: int | None = None
    exited_at: datetime | None = None
    stderr_log_path: str | None = None


class WorkerLaunchSpec(BaseModel):
    """Minimal JSON contract used to launch a SubAgent worker process."""

    model_config = ConfigDict(extra="ignore")

    run_id: str
    run_store_dir: str
    workspace_dir: str
    parent_agent_config: dict[str, Any]
    definition: SubAgentDefinition
    delegation_spec: DelegationSpec
    effective_policy: PermissionPolicy
    start_request: SubAgentStartRequest | None = None
    definition_match: DefinitionMatchMetadata = Field(
        default_factory=DefinitionMatchMetadata,
    )
    nickname: str | None = None
    request_context: dict[str, Any] = Field(default_factory=dict)
    stderr_log_path: str | None = None

    @model_validator(mode="after")
    def keep_only_safe_request_context(self) -> "WorkerLaunchSpec":
        self.parent_agent_config = _drop_secret_like_fields(
            self.parent_agent_config,
        )
        self.request_context = {
            key: value
            for key, value in self.request_context.items()
            if key in SAFE_WORKER_REQUEST_CONTEXT_KEYS
        }
        return self


class BackgroundSubAgentRunRecord(BaseModel):
    """Per-run persisted record for an observable Background SubAgent Run."""

    run_id: str = Field(default_factory=lambda: f"subagent-{uuid4().hex[:12]}")
    status: BackgroundRunStatus = "pending"
    spec: DelegationSpec
    definition_name: str
    definition_version: str
    definition_source: DefinitionSource
    owner_scope: str
    effective_policy: PermissionPolicy
    effective_budget: BudgetConfig = Field(default_factory=BudgetConfig)
    nickname: str | None = None
    start_request: SubAgentStartRequest | None = None
    definition_match: DefinitionMatchMetadata = Field(
        default_factory=DefinitionMatchMetadata,
    )
    worker: WorkerProcessInfo | None = None
    result: AgentResult | None = None
    errors: list[AgentError] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now_utc)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=_now_utc)
