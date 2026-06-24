import { request } from "../request";
import { buildAuthHeaders } from "../authHeaders";

/**
 * 市场 MCP 版本管理 API（与 skillVersionApi 对称）。
 *
 * 后端：market/src/market/app/routers/mcp_versions.py
 * 设计：docs/superpowers/specs/2026-06-13-skill-mcp-version-control-design.md §6.3
 */

export interface MCPVersion {
  version_id: string;
  created_at: string;
  created_by: string;
  created_by_name: string;
  description: string;
  signature: string;
  is_current: boolean;
  is_initial: boolean;
  source_user_id: string;
  source_user_name: string;
  source_user_version: string;
}

export interface MCPVersionsManifest {
  client_key: string;
  name: string;
  versions: MCPVersion[];
}

export interface MCPVersionSwitchResult {
  success: boolean;
  previous_version: string;
  current_version: string;
  message: string;
}

export interface MCPVersionDeleteResult {
  success: boolean;
  deleted_version: string;
  message: string;
}

export interface MCPVersionDiffStats {
  added_lines: number;
  deleted_lines: number;
  changed_files: number;
}

export interface MCPVersionDiffFile {
  path: string;
  added_lines: number;
  deleted_lines: number;
  diff: string;
  original_content: string;
  modified_content: string;
}

export interface MCPVersionCompareResult {
  base_version: string;
  target_version: string;
  stats: MCPVersionDiffStats;
  files: MCPVersionDiffFile[];
}

export const marketMcpVersionApi = {
  /**
   * 获取 MCP 版本历史列表
   */
  listVersions: async (
    sourceId: string,
    itemId: string,
  ): Promise<MCPVersionsManifest> => {
    const headers = new Headers(buildAuthHeaders());
    headers.set("X-Source-Id", sourceId);
    return request<MCPVersionsManifest>(
      `/market/mcp/${itemId}/versions`,
      {
        method: "GET",
        headers,
      },
    );
  },

  /**
   * 切换到指定 MCP 版本（管理员）
   */
  switchVersion: async (
    sourceId: string,
    itemId: string,
    versionId: string,
  ): Promise<MCPVersionSwitchResult> => {
    const headers = new Headers(buildAuthHeaders());
    headers.set("X-Source-Id", sourceId);
    headers.set("X-Manager", "true");
    return request<MCPVersionSwitchResult>(
      `/market/mcp/${itemId}/versions/${versionId}/switch`,
      {
        method: "POST",
        headers,
      },
    );
  },

  /**
   * 删除指定 MCP 版本快照（管理员）
   */
  deleteVersion: async (
    sourceId: string,
    itemId: string,
    versionId: string,
  ): Promise<MCPVersionDeleteResult> => {
    const headers = new Headers(buildAuthHeaders());
    headers.set("X-Source-Id", sourceId);
    headers.set("X-Manager", "true");
    return request<MCPVersionDeleteResult>(
      `/market/mcp/${itemId}/versions/${versionId}`,
      {
        method: "DELETE",
        headers,
      },
    );
  },

  /**
   * 比对两个 MCP 版本（仅 mcp.json）
   */
  compareVersions: async (
    sourceId: string,
    itemId: string,
    baseVersionId: string,
    targetVersionId: string,
  ): Promise<MCPVersionCompareResult> => {
    const headers = new Headers(buildAuthHeaders());
    headers.set("X-Source-Id", sourceId);
    headers.set("Content-Type", "application/json");
    return request<MCPVersionCompareResult>(
      `/market/mcp/${itemId}/versions/compare`,
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
};
