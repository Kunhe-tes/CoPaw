export type ApprovalStatus =
  | "missing"
  | "pending"
  | "submitted"
  | "approved"
  | "denied"
  | "timeout"
  | "superseded";

export interface ApprovalStatusResponse {
  request_id: string;
  status: ApprovalStatus | string;
  session_id?: string | null;
  decision?: string | null;
  source_channel?: string | null;
  source_user_id?: string | null;
  source_message_id?: string | null;
  submitted_at?: number | null;
}
