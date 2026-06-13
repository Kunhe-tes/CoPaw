import { request } from "../request";
import { buildAuthHeaders } from "../authHeaders";

export interface SkillVersion {
  version_id: string;
  created_at: string;
  created_by: string;
  description: string;
  signature: string;
  is_current: boolean;
  is_initial: boolean;
}

export interface VersionsManifest {
  skill_name: string;
  versions: SkillVersion[];
}

export interface VersionDiffStats {
  added_lines: number;
  deleted_lines: number;
  changed_files: number;
}

export interface VersionDiffFile {
  path: string;
  added_lines: number;
  deleted_lines: number;
  diff: string;
  original_content: string;
  modified_content: string;
}

export interface VersionCompareResult {
  base_version: string;
  target_version: string;
  stats: VersionDiffStats;
  files: VersionDiffFile[];
}

export interface VersionSwitchResult {
  success: boolean;
  previous_version: string;
  current_version: string;
  message: string;
}

export interface VersionDeleteResult {
  success: boolean;
  deleted_version: string;
  message: string;
}

export interface VersionCompareRequest {
  base_version_id: string;
  target_version_id: string;
}

export interface VersionDetail {
  version_info: SkillVersion;
  file_tree: FileTreeNode[];
}

export interface FileTreeNode {
  name: string;
  type: "file" | "directory";
  path: string;
  children?: FileTreeNode[];
}

export const skillVersionApi = {
  /**
   * 获取技能版本历史列表
   */
  listVersions: async (
    sourceId: string,
    itemId: string,
  ): Promise<VersionsManifest> => {
    const headers = new Headers(buildAuthHeaders());
    headers.set("X-Source-Id", sourceId);
    return request<VersionsManifest>(
      `/market/skills/${itemId}/versions`,
      {
        method: "GET",
        headers,
      },
    );
  },

  /**
   * 获取单个版本详情
   */
  getVersionDetail: async (
    sourceId: string,
    itemId: string,
    versionId: string,
  ): Promise<VersionDetail> => {
    const headers = new Headers(buildAuthHeaders());
    headers.set("X-Source-Id", sourceId);
    return request<VersionDetail>(
      `/market/skills/${itemId}/versions/${versionId}`,
      {
        method: "GET",
        headers,
      },
    );
  },

  /**
   * 切换到指定版本
   */
  switchVersion: async (
    sourceId: string,
    itemId: string,
    versionId: string,
  ): Promise<VersionSwitchResult> => {
    const headers = new Headers(buildAuthHeaders());
    headers.set("X-Source-Id", sourceId);
    headers.set("X-Manager", "true");
    return request<VersionSwitchResult>(
      `/market/skills/${itemId}/versions/${versionId}/switch`,
      {
        method: "POST",
        headers,
      },
    );
  },

  /**
   * 比对两个版本
   */
  compareVersions: async (
    sourceId: string,
    itemId: string,
    baseVersionId: string,
    targetVersionId: string,
  ): Promise<VersionCompareResult> => {
    const headers = new Headers(buildAuthHeaders());
    headers.set("X-Source-Id", sourceId);
    headers.set("Content-Type", "application/json");
    return request<VersionCompareResult>(
      `/market/skills/${itemId}/versions/compare`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({
          base_version_id: baseVersionId,
          target_version_id: targetVersionId,
        }),
      },
    );
  },

  /**
   * 删除指定版本
   */
  deleteVersion: async (
    sourceId: string,
    itemId: string,
    versionId: string,
  ): Promise<VersionDeleteResult> => {
    const headers = new Headers(buildAuthHeaders());
    headers.set("X-Source-Id", sourceId);
    headers.set("X-Manager", "true");
    return request<VersionDeleteResult>(
      `/market/skills/${itemId}/versions/${versionId}`,
      {
        method: "DELETE",
        headers,
      },
    );
  },
};