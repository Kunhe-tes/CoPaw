export interface EnvVar {
  key: string;
  value: string;
}

export interface EnvPatchRequest {
  values: Record<string, string>;
  preserve?: string[];
  delete: string[];
}
