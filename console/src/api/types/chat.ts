export type ChatStatus = "idle" | "running" | "stopping";

export interface ChatSpec {
  id: string; // Chat UUID identifier
  session_id: string; // Session identifier (channel:user_id format)
  user_id: string; // User identifier
  channel: string; // Channel name, default: "default"
  name?: string; // Chat display name
  created_at: string | null; // Chat creation timestamp (ISO 8601)
  updated_at: string | null; // Chat last update timestamp (ISO 8601)
  meta?: Record<string, unknown>; // Additional metadata
  status?: ChatStatus; // Conversation status: idle, running, or stopping
}

export interface Message {
  role: string;
  content: unknown;
  timestamp?: string | null;
  [key: string]: unknown;
}

export interface ChatHistory {
  chat?: ChatSpec | null;
  messages: Message[];
  status?: ChatStatus; // Conversation status: idle, running, or stopping
  archive?: ChatArchiveMetadata;
}

export interface ChatCompactionBoundary {
  id: string;
  archived_message_count: number;
  first_message_id: string;
  last_message_id: string;
  created_at: string;
  first_timestamp?: string | null;
  last_timestamp?: string | null;
}

export interface ChatArchiveMetadata {
  has_more: boolean;
  boundaries: ChatCompactionBoundary[];
}

export interface ChatArchivePage extends ChatArchiveMetadata {
  messages: Message[];
  next_cursor?: string | null;
}

export interface ChatPage {
  items: ChatSpec[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
  next_cursor?: string | null;
}

export interface ChatDeleteResponse {
  success: boolean;
  chat_id: string;
}

// Legacy Session type alias for backward compatibility
export type Session = ChatSpec;
