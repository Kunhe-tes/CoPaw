import { request } from "../request";
import type { SkillMentionItem } from "@/components/agentscope-chat/SkillMentions/useSkillMentions";

export interface ContextReferencesResponse {
  skills: SkillMentionItem[];
  mcp_tools: SkillMentionItem[];
  files: SkillMentionItem[];
}

export const contextReferencesApi = {
  discover: (query = "") =>
    request<ContextReferencesResponse>(
      `/console/context-references${
        query ? `?q=${encodeURIComponent(query)}` : ""
      }`,
    ),
};
