import { getApiToken } from "./config";
import { getExternalToken, isExternalTokenEnabled } from "./externalToken";

// ==================== userId 统一整改 (Kun He) ====================
// 使用统一的 getUserId helper，遵循优先级：iframe > window > session > default
import { getUserId } from "../utils/identity";
import { getIframeContext } from "../stores/iframeStore";
import { DEFAULT_SOURCE_ID, DEFAULT_BBK_ID, DEFAULT_USER_NAME } from "../constants/identity";
import { COOKIE_KEYS } from "../layouts/constants";
// ==================== userId 统一整改结束 ====================

/**
 * 构建认证和上下文相关的请求 headers
 *
 * 包含：
 * - Authorization: Bearer token
 * - X-Agent-Id: 当前选中的 agent
 * - X-User-Id: 用户 ID（来自 iframe userId，默认 "default"）
 * - X-Tenant-Id: 租户 ID（与 X-User-Id 保持一致）
 * - 自定义 headers（来自 iframe auth 数组）
 */
export function buildAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};

  // 1. Token（优先级：外部系统 token > localStorage > iframe context）
  // 优先使用外部系统 token（如果启用）
  if (isExternalTokenEnabled()) {
    const externalToken = getExternalToken();
    if (externalToken) {
      headers['X-Auth-Authorization'] = `Bearer ${externalToken}`;
    }
  } else {
    // 回退到原有 token 逻辑
    const token = getApiToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  // 2. Agent ID（从 sessionStorage 读取当前选中的 agent）
  try {
    const agentStorage = sessionStorage.getItem("swe-agent-storage");
    if (agentStorage) {
      const parsed = JSON.parse(agentStorage);
      const selectedAgent = parsed?.state?.selectedAgent;
      if (selectedAgent) {
        headers["X-Agent-Id"] = selectedAgent;
      }
    }
  } catch (error) {
    console.warn("Failed to get selected agent from storage:", error);
  }

  // 3. 用户 ID 和租户 ID
  // ==================== userId 统一整改 (Kun He) ====================
  // 使用统一的 getUserId() 获取用户 ID
  // 优先级：iframe userId > window.currentUserId > DEFAULT_USER_ID
  // X-Tenant-Id 与 X-User-Id 保持一致
  const userId = getUserId();
  headers["X-User-Id"] = userId;
  headers["X-Tenant-Id"] = userId;

  // 4. 自定义 headers 数组（父窗口通过 auth 字段传递）
  // 注意：排除 X-User-Id，因为已由 getUserId() 处理
  const iframeContext = getIframeContext();
  if (iframeContext.isSuperManager) {
    headers["X-User-Role"] = "admin";
  } else if (iframeContext.manager) {
    headers["X-User-Role"] = "manager";
  }

  if (iframeContext.authHeaders?.length) {
    for (const item of iframeContext.authHeaders) {
      // 跳过 X-User-Id，避免覆盖上面设置的值
      if (
        item.headerName &&
        item.headerValue !== undefined &&
        item.headerName !== "X-User-Id" &&
        item.headerName !== "X-User-Role"
      ) {
        headers["x-header-" + item.headerName] = item.headerValue;
      }
    }
  }
  // ==================== userId 统一整改结束 ====================

  // 5. Source ID（来自 iframe context，用于数据隔离）
  // 独立访问时也必须携带默认 source，避免后端严格隔离校验直接拒绝请求
  const sourceId = iframeContext.source || DEFAULT_SOURCE_ID;
  if (sourceId) {
    headers["X-Source-Id"] = sourceId;
  }

  // 6. BBK ID（来自 iframe context，用于维度配置匹配）
  // 非 iframe 模式下使用 DEFAULT_BBK_ID
  const bbkId = iframeContext.bbk || DEFAULT_BBK_ID;
  if (bbkId) {
    headers["X-Bbk-Id"] = bbkId;
  }

  // 7. Scope ID（tenantId和sourceId拼接而成）
  headers["X-Scope-Id"] = `${userId}-${sourceId}`

  // 8. Username
  const userName = iframeContext.userName || DEFAULT_USER_NAME
  if (userName) {
    headers["X-User-Name"] = encodeURIComponent(userName);
  }

  // 反馈落库需要保留支行与岗位信息，随请求上下文一起透传给后端。
  if (iframeContext.orgCode) {
    headers["X-Org-Code"] = iframeContext.orgCode;
  }
  if (iframeContext.positionId) {
    headers["X-Position-Id"] = iframeContext.positionId;
  }

  // 9. Space（来自 iframe context）
  if (iframeContext.space) {
    headers["space"] = iframeContext.space;
  }

  // 10. Cookie（优先使用 iframeContext 中 userChange=true 时的值，否则使用 document.cookie）
  let cookieData;
  // 定义需要替换的cookie key映射关系
  const cookieKeyMap: Record<string, string> = {
    'userId': COOKIE_KEYS.userId,
    'sysId': COOKIE_KEYS.sysId,
    'bbk': COOKIE_KEYS.bbk,
    'orgCode': COOKIE_KEYS.orgCode,
    'orgLvl': COOKIE_KEYS.orgLvl,
    'token': COOKIE_KEYS.token,
    'positionId': COOKIE_KEYS.positionId
  };

  if (iframeContext.userChange) {
    // 优先使用 iframeContext 中的值（从 fetchCustomerInfo 接口获取的最新cookie）
    let cookieString = document.cookie;
    Object.entries(iframeContext).forEach(([key, value]) => {
      if (key in cookieKeyMap && value) {
        const cookieKey = cookieKeyMap[key as keyof typeof cookieKeyMap];
        const searchRegex = new RegExp(`${cookieKey}=[^;]*`, 'g');

        if (cookieString.includes(cookieKey)) {
          // 如果cookie中存在该key，替换其值
          cookieString = cookieString.replace(searchRegex, `${cookieKey}=${encodeURIComponent(value)}`);
        } else {
          // 如果cookie中不存在该key，添加新的cookie
          cookieString += `; ${cookieKey}=${encodeURIComponent(value)}`;
        }
      }
    });
    cookieData = cookieString;
  } else {
    // 未变更时，直接使用 document.cookie（浏览器会自动更新过期的cookie）
    cookieData = document.cookie;
  }

  headers["x-header-cookie"] = cookieData;

  return headers;
}
