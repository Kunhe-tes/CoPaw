import { request } from "../request";
import { getApiUrl, getApiToken } from "../config";
import { buildAuthHeaders } from "../authHeaders";
import type {
  ChatPage,
  ChatSpec,
  ChatHistory,
  ChatDeleteResponse,
  Session,
} from "../types";

/** Response from POST /console/upload. url = filename only; agent_id from header. */
export interface ChatUploadResponse {
  url: string;
  file_name: string;
  stored_name?: string;
}

export interface GeneratedFileItem {
  name: string;
  display_name: string;
  relative_path: string;
  file_url: string;
  size: number;
  modified_at: string;
  mime_type?: string | null;
  preview_type:
    | "image"
    | "video"
    | "audio"
    | "office"
    | "pdf"
    | "markdown"
    | "text"
    | "html"
    | "other";
  source: "generated" | "uploaded";
}

export interface GeneratedFilesResponse {
  files: GeneratedFileItem[];
}

const FILES_PREVIEW = "/files/preview";

export const chatApi = {
  /** Upload a file for chat attachment. Returns URL path for content. */
  uploadFile: async (file: File): Promise<ChatUploadResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(getApiUrl("/console/upload"), {
      method: "POST",
      headers: buildAuthHeaders(),
      body: formData,
    });
    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new Error(
        `Upload failed: ${response.status} ${response.statusText}${
          text ? ` - ${text}` : ""
        }`,
      );
    }
    return response.json();
  },

  filePreviewUrl: (filename: string): string => {
    if (!filename) return "";
    if (filename.startsWith("http://") || filename.startsWith("https://"))
      return filename;
    const path = `${FILES_PREVIEW}/${filename.replace(/^\/+/, "")}`;
    const url = getApiUrl(path);

    const token = getApiToken();
    if (token) {
      return `${url}?token=${encodeURIComponent(token)}`;
    }

    return url;
  },
  listChats: (params?: { user_id?: string; channel?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.user_id) searchParams.append("user_id", params.user_id);
    if (params?.channel) searchParams.append("channel", params.channel);
    const query = searchParams.toString();
    return request<ChatSpec[]>(`/chats${query ? `?${query}` : ""}`);
  },

  listChatsPage: (params: {
    page_size: number;
    page?: number;
    cursor?: string | null;
    user_id?: string;
    channel?: string;
    exclude_session_kind?: string;
  }) => {
    const searchParams = new URLSearchParams({
      page_size: String(params.page_size),
    });
    if (params.page !== undefined) {
      searchParams.append("page", String(params.page));
    }
    if (params.cursor !== undefined) {
      searchParams.append("cursor", params.cursor || "");
    }
    if (params.user_id) searchParams.append("user_id", params.user_id);
    if (params.channel) searchParams.append("channel", params.channel);
    if (params.exclude_session_kind) {
      searchParams.append("exclude_session_kind", params.exclude_session_kind);
    }
    return request<ChatPage>(`/chats?${searchParams.toString()}`);
  },

  createChat: (chat: Partial<ChatSpec>) =>
    request<ChatSpec>("/chats", {
      method: "POST",
      body: JSON.stringify(chat),
    }),

  getChat: (chatId: string) =>
    request<ChatHistory>(`/chats/${encodeURIComponent(chatId)}`),

  updateChat: (chatId: string, chat: Partial<ChatSpec>) =>
    request<ChatSpec>(`/chats/${encodeURIComponent(chatId)}`, {
      method: "PUT",
      body: JSON.stringify(chat),
    }),

  deleteChat: (chatId: string) =>
    request<ChatDeleteResponse>(`/chats/${encodeURIComponent(chatId)}`, {
      method: "DELETE",
    }),

  batchDeleteChats: (chatIds: string[]) =>
    request<{ success: boolean; deleted_count: number }>(
      "/chats/batch-delete",
      {
        method: "POST",
        body: JSON.stringify(chatIds),
      },
    ),

  listGeneratedFiles: (
    sort: "asc" | "desc" = "desc",
    source: "all" | "generated" | "uploaded" = "all",
  ) =>
    request<GeneratedFilesResponse>(
      `/console/generated-files?sort=${encodeURIComponent(
        sort,
      )}&source=${encodeURIComponent(source)}`,
    ),

  stopChat: (chatId: string) =>
    request<void>(`/console/chat/stop?chat_id=${encodeURIComponent(chatId)}`, {
      method: "POST",
    }),
};

export const sessionApi = {
  listSessions: (params?: { user_id?: string; channel?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.user_id) searchParams.append("user_id", params.user_id);
    if (params?.channel) searchParams.append("channel", params.channel);
    const query = searchParams.toString();
    return request<Session[]>(`/chats${query ? `?${query}` : ""}`);
  },

  getSession: (sessionId: string) =>
    request<ChatHistory>(`/chats/${encodeURIComponent(sessionId)}`),

  deleteSession: (sessionId: string) =>
    request<ChatDeleteResponse>(`/chats/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    }),

  createSession: (session: Partial<Session>) =>
    request<Session>("/chats", {
      method: "POST",
      body: JSON.stringify(session),
    }),

  updateSession: (sessionId: string, session: Partial<Session>) =>
    request<Session>(`/chats/${encodeURIComponent(sessionId)}`, {
      method: "PUT",
      body: JSON.stringify(session),
    }),

  batchDeleteSessions: (sessionIds: string[]) =>
    request<{ success: boolean; deleted_count: number }>(
      "/chats/batch-delete",
      {
        method: "POST",
        body: JSON.stringify(sessionIds),
      },
    ),
};
