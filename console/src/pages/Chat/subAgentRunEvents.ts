const SUBAGENT_TOOL_NAMES = new Set([
  "start_subagent",
  "wait_subagent",
  "get_subagent",
  "cancel_subagent",
]);

export const SUBAGENT_RUNS_REFRESH_EVENT = "subagent-runs-refresh";

function containsSubAgentToolName(value: unknown, depth = 0): boolean {
  if (depth > 6 || value === null || value === undefined) return false;
  if (typeof value === "string") {
    return SUBAGENT_TOOL_NAMES.has(value);
  }
  if (Array.isArray(value)) {
    return value.some((item) => containsSubAgentToolName(item, depth + 1));
  }
  if (typeof value !== "object") return false;
  return Object.entries(value as Record<string, unknown>).some(
    ([key, item]) =>
      ((key === "name" || key === "tool_name") &&
        typeof item === "string" &&
        SUBAGENT_TOOL_NAMES.has(item)) ||
      containsSubAgentToolName(item, depth + 1),
  );
}

export function emitSubAgentRunsRefreshIfPresent(value: unknown): void {
  if (!containsSubAgentToolName(value)) return;
  document.dispatchEvent(new CustomEvent(SUBAGENT_RUNS_REFRESH_EVENT));
}
