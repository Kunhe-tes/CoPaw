export interface SourceSystemConfig extends Record<string, unknown> {
  system_prompt_injections?: string[];
  approval_notifications?: {
    zhaohu_tool_guard_enabled?: boolean;
    [key: string]: unknown;
  };
}

export interface EffectiveSourceSystemConfig {
  source_id: string;
  config: SourceSystemConfig;
  version: number;
  is_default: boolean;
  stale: boolean;
  last_error?: string | null;
  updated_by?: string | null;
  updated_at?: string | null;
}

export interface CurrentSourceSystemConfigResponse {
  source_id: string;
  config: SourceSystemConfig;
  version: number;
  is_default: boolean;
  updated_by?: string | null;
  updated_at?: string | null;
}

export interface CurrentSourceSystemConfigUpdateRequest {
  config: SourceSystemConfig;
}
