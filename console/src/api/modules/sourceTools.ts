import { request } from "../request";

export interface SourceToolMetadata {
  name: string;
  version: number;
  description: string;
  json_schema: Record<string, unknown>;
  required_env: string[];
  content_digest: string;
  active: boolean;
  origin: "source";
}

export interface SourceToolDraft {
  name: string;
  description: string;
  json_schema: Record<string, unknown>;
  required_env: string[];
  content_digest: string;
  created_at: number;
  created_by: string | null;
  status: "draft";
}

export interface SourceToolVersion extends SourceToolDraft {
  version: number;
}

export interface SourceToolAuditEvent {
  event: string;
  source_id: string;
  tool_name: string;
  actor: string | null;
  timestamp: number;
  version: number | null;
  content_digest: string | null;
}

const toolPath = (suffix: string) => "/source-tools/" + suffix;

export const sourceToolsApi = {
  listEffective: () => request<SourceToolMetadata[]>(toolPath("effective")),
  listDrafts: () => request<SourceToolDraft[]>(toolPath("drafts")),
  uploadDraft: (file: File, replaceDraft = false) => {
    const body = new FormData();
    body.set("file", file);
    body.set("replace_draft", String(replaceDraft));
    return request<SourceToolDraft>(toolPath("drafts"), {
      method: "POST",
      body,
    });
  },
  discardDraft: (name: string) =>
    request<void>(toolPath("drafts/" + encodeURIComponent(name)), {
      method: "DELETE",
    }),
  publishDraft: (name: string, confirmReplace = false) => {
    const body = new FormData();
    body.set("confirm_replace", String(confirmReplace));
    return request<SourceToolVersion>(
      toolPath("drafts/" + encodeURIComponent(name) + "/publish"),
      { method: "POST", body },
    );
  },
  manualTest: (name: string, argumentsInput: Record<string, unknown>) =>
    request<{ output: unknown }>(
      toolPath("drafts/" + encodeURIComponent(name) + "/manual-test"),
      {
        method: "POST",
        body: JSON.stringify({
          confirmed: true,
          arguments: argumentsInput,
        }),
      },
    ),
  deactivate: (name: string) =>
    request<void>(
      toolPath("active/" + encodeURIComponent(name) + "/deactivate"),
      { method: "POST" },
    ),
  history: (name: string) =>
    request<SourceToolVersion[]>(
      toolPath("history/" + encodeURIComponent(name)),
    ),
  audit: () => request<SourceToolAuditEvent[]>(toolPath("audit")),
  downloadDraft: (name: string) =>
    request<{ content: string }>(
      toolPath("drafts/" + encodeURIComponent(name) + "/download"),
    ),
  downloadVersion: (name: string, version: number) =>
    request<{ content: string }>(
      toolPath(
        "history/" + encodeURIComponent(name) + "/" + version + "/download",
      ),
    ),
};
