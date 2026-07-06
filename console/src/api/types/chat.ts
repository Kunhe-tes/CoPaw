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

export type SubAgentRunStatus =
  | "pending"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled"
  | "expired";

export interface SubAgentBudgetConsumption {
  elapsed_ms: number;
  timeout_ms: number;
  ratio: number;
}

export interface SubAgentRunSnapshotItem {
  run_id: string;
  agent_name: string;
  nickname?: string | null;
  objective: string;
  status: SubAgentRunStatus;
  stoppable: boolean;
  definition_match?: {
    matched: boolean;
    definition_name?: string | null;
    definition_source?: string | null;
    score?: number | null;
    reason?: string | null;
  };
  budget_consumption: SubAgentBudgetConsumption;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  summary_preview?: string | null;
  error_preview?: string | null;
}

export interface SubAgentRunSnapshot {
  chat_id: string;
  session_id: string;
  runs: SubAgentRunSnapshotItem[];
}

export interface SubAgentRunCancelResponse {
  run: SubAgentRunSnapshotItem;
}

// Legacy Session type alias for backward compatibility
export type Session = ChatSpec;
