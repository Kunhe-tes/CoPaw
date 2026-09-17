import { describe, expect, it } from "vitest";
import type { SkillMentionItem } from "../../components/agentscope-chat/SkillMentions/useSkillMentions";
import { selectContextReferences } from "./contextReferenceDefaults";

const items: SkillMentionItem[] = [
  ...Array.from({ length: 4 }, (_, index) => ({
    id: `skill:${index}`,
    type: "skill" as const,
    label: `skill-${index}`,
    name: `skill-${index}`,
    description: "skill",
  })),
  ...Array.from({ length: 4 }, (_, index) => ({
    id: `mcp:${index}`,
    type: "mcp_tool" as const,
    label: `mcp-${index}`,
    name: `mcp-${index}`,
    server: "server",
    description: "tool",
  })),
  {
    id: "file:report.txt",
    type: "workspace_file" as const,
    label: "report.txt",
    description: "report.txt",
  },
];

describe("selectContextReferences", () => {
  it("shows all skills, at most three MCP tools, and no files for the initial menu", () => {
    expect(selectContextReferences(items, "")).toEqual(items.slice(0, 7));
  });

  it("keeps search results unchanged when a query is provided", () => {
    expect(selectContextReferences(items, "report")).toEqual(items);
  });
});
