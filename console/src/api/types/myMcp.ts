/**
 * 我的 MCP 管理相关类型定义
 */

/** MCP 列表项 */
export interface MyMCPListItem {
  /** 唯一标识 key */
  client_key: string;
  /** 显示名称 */
  name: string;
  /** 描述 */
  description: string;
  /** MCP 传输类型 */
  transport: "stdio" | "streamable_http" | "sse";
  /** 是否启用 */
  enabled: boolean;
  /** 来源（本地/市场） */
  source: string;
  /** 市场原始 client_key */
  market_client_key: string;
  /** 创建时间 */
  created_at: string;
  /** 更新时间 */
  updated_at: string;
}

/** MCP 详情 */
export interface MyMCPDetail extends MyMCPListItem {
  /** HTTP/SSE URL */
  url: string;
  /** HTTP headers（脱敏展示） */
  headers: Record<string, string>;
  /** stdio 命令 */
  command: string;
  /** 命令行参数 */
  args: string[];
  /** 环境变量（脱敏展示） */
  env: Record<string, string>;
  /** 工作目录 */
  cwd: string;
  /** 是否懒加载 */
  lazy_load: boolean;
  /** 分发来源 */
  distributed_by: string;
}

/** MCP 创建请求 */
export interface MyMCPCreateRequest {
  /** 唯一标识 key */
  client_key: string;
  /** 显示名称 */
  name: string;
  /** 描述 */
  description?: string;
  /** MCP 传输类型 */
  transport?: "stdio" | "streamable_http" | "sse";
  /** HTTP/SSE URL */
  url?: string;
  /** HTTP headers */
  headers?: Record<string, string>;
  /** stdio 命令 */
  command?: string;
  /** 命令行参数 */
  args?: string[];
  /** 环境变量 */
  env?: Record<string, string>;
  /** 工作目录 */
  cwd?: string;
  /** 是否懒加载 */
  lazy_load?: boolean;
}

/** MCP 更新请求 */
export interface MyMCPUpdateRequest {
  /** 显示名称 */
  name?: string;
  /** 描述 */
  description?: string;
  /** MCP 传输类型 */
  transport?: "stdio" | "streamable_http" | "sse";
  /** HTTP/SSE URL */
  url?: string;
  /** HTTP headers */
  headers?: Record<string, string>;
  /** stdio 命令 */
  command?: string;
  /** 命令行参数 */
  args?: string[];
  /** 环境变量 */
  env?: Record<string, string>;
  /** 工作目录 */
  cwd?: string;
  /** 是否懒加载 */
  lazy_load?: boolean;
}

/** MCP 草稿测试请求 */
export interface MyMCPDraftTestRequest {
  /** 编辑场景下的原始 client_key，用于恢复脱敏字段 */
  baseline_client_key?: string;
  /** 显示名称 */
  name?: string;
  /** MCP 传输类型 */
  transport?: "stdio" | "streamable_http" | "sse";
  /** HTTP/SSE URL */
  url?: string;
  /** HTTP headers */
  headers?: Record<string, string>;
  /** stdio 命令 */
  command?: string;
  /** 命令行参数 */
  args?: string[];
  /** 环境变量 */
  env?: Record<string, string>;
  /** 工作目录 */
  cwd?: string;
}

/** 发布到市场请求 */
export interface PublishMCPRequest {
  /** 要发布的 client_key 列表 */
  client_keys: string[];
  /** 分类 ID */
  category_id?: number;
  /** 关联 BBK ID 列表 */
  bbk_ids?: string[];
}

/** 单个 MCP 发布到市场请求 */
export interface PublishSingleMCPRequest {
  /** 分类 ID */
  category_id?: number;
  /** 关联 BBK ID 列表 */
  bbk_ids?: string[];
  /** 同名 MCP 已存在时是否覆盖 */
  overwrite?: boolean;
}

/** 单个发布结果 */
export interface PublishMCPResult {
  /** MCP client key */
  client_key: string;
  /** 市场 item ID */
  item_id?: string;
  /** 是否成功 */
  success: boolean;
  /** 错误信息 */
  error?: string;
}

/** 发布响应 */
export interface PublishMCPResponse {
  /** 发布结果列表 */
  results: PublishMCPResult[];
}

/** 单个发布响应 */
export interface PublishSingleMCPResponse {
  /** MCP client key */
  client_key: string;
  /** 市场 item ID */
  item_id: string;
  /** 是否成功 */
  success: boolean;
}

/** MCP 测试连接结果 */
export interface MCPTestResult {
  /** 连接是否成功 */
  success: boolean;
  /** 可用工具列表 */
  tools: Array<{
    name: string;
    description: string;
  }>;
  /** 错误信息 */
  error: string;
}
