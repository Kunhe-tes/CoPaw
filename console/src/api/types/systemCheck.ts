export type CronAuthExpiryStatus =
  | "valid"
  | "expired"
  | "missing_file"
  | "invalid_content"
  | "unknown";

export interface CronAuthExpiryRequest {
  source_id: string;
  tenant_ids: string[];
}

export interface CronAuthExpiryResult {
  tenant_id: string;
  source_id: string;
  status: CronAuthExpiryStatus;
  is_expired: boolean | null;
  user_info_expires_at: string | null;
  message: string;
}

export interface CronAuthExpiryResponse {
  results: CronAuthExpiryResult[];
}
