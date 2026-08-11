import type { SkillMentionItem } from "../../components/agentscope-chat/SkillMentions/useSkillMentions";

const INITIAL_MCP_TOOL_LIMIT = 3;

export function selectContextReferences(
  references: SkillMentionItem[],
  query: string,
): SkillMentionItem[] {
  if (query.trim()) return references;

  const skills = references.filter((reference) => reference.type === "skill");
  const mcpTools = references
    .filter((reference) => reference.type === "mcp_tool")
    .slice(0, INITIAL_MCP_TOOL_LIMIT);

  return [...skills, ...mcpTools];
}
