# Run-scoped SubAgent Definitions And Stored Definition Routing

**Status:** Superseded by ADR 0024.

SubAgent start requests will use a compact Main Agent tool contract with `name`, `instruction`, `objective`, and optional `background`; this request creates a Run-scoped SubAgent Definition unless deterministic matching can short-circuit to an enabled stored or built-in definition. The start request does not accept `nickname`, registration-only routing metadata, budgets, tools, permissions, or output contracts; those belong to the Stored SubAgent Definition registration surface.

SubAgent Definition terminology and runtime records use `instruction` and `name` as canonical fields, not `system_prompt`, `prompt.system`, or `agent_name`. The internal definition sources are `builtin`, `stored`, and `run_scoped`; no backward compatibility is kept for the old field names because preserving both vocabularies would keep the Main Agent producing unstable payloads.

Stored definitions are registered through a management-facing entry point backed by a shared definition service. The first store is tenant-and-agent scoped, one JSON file per definition, with whole-object upsert semantics and no cross-pod registry consistency guarantee. Stored definitions may configure `nickname`; when a run has no configured nickname, the runtime assigns one from a built-in nickname pool and writes it to the run record.

Start-time matching uses deterministic rules over `name`, `objective`, `background`, and candidate `name`, `trigger_keywords`, and `description`; it does not use `instruction` for scoring and does not call an embedding or LLM matcher. If no confident match is selected, including disabled or ambiguous candidates, the runtime falls back to the Run-scoped SubAgent Definition rather than returning `unknown_subagent`. Run records and status responses include definition match metadata so later readers can tell whether an existing definition was reused or the compact request ran as a one-off worker.
