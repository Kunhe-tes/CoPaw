const START_SUBAGENT_TOOL_NAMES = new Set(["start_subagent"]);
const SUBAGENT_TOOL_NAMES = new Set([
  "start_subagent",
  "wait_subagent",
  "get_subagent",
  "cancel_subagent",
]);

export const SUBAGENT_RUNS_REFRESH_EVENT = "subagent-runs-refresh";

function containsSubAgentToolName(
  value: unknown,
  depth = 0,
  toolNames = SUBAGENT_TOOL_NAMES,
): boolean {
  if (depth > 6 || value === null || value === undefined) return false;
  if (typeof value === "string") {
    return toolNames.has(value);
  }
  if (Array.isArray(value)) {
    return value.some((item) =>
      containsSubAgentToolName(item, depth + 1, toolNames),
    );
  }
  if (typeof value !== "object") return false;
  return Object.entries(value as Record<string, unknown>).some(
    ([key, item]) =>
      ((key === "name" || key === "tool_name") &&
        typeof item === "string" &&
        toolNames.has(item)) ||
      containsSubAgentToolName(item, depth + 1, toolNames),
  );
}

export function emitSubAgentRunsRefreshIfPresent(
  value: unknown,
  chatId?: string | null,
): void {
  if (!containsSubAgentToolName(value)) return;
  emitSubAgentRunsRefresh(
    chatId,
    containsSubAgentToolName(value, 0, START_SUBAGENT_TOOL_NAMES),
  );
}

export function emitSubAgentRunsRefresh(
  chatId: string | null | undefined,
  discover: boolean,
): void {
  document.dispatchEvent(
    new CustomEvent(SUBAGENT_RUNS_REFRESH_EVENT, {
      detail: { chatId, discover },
    }),
  );
}
