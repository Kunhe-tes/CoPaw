import { DEFAULT_SOURCE_ID } from "../../constants/identity";
import { getIframeContext } from "../../stores/iframeStore";
import { getUserId } from "../../utils/identity";
import { buildAuthHeaders } from "../authHeaders";
import { getApiUrl } from "../config";
import { request } from "../request";
import type {
  HtmlPreviewCustomerClickResponse,
  HtmlPreviewClickEventListResponse,
  HtmlPreviewClickEventPayload,
  HtmlPreviewClickSubmitResponse,
  HtmlPreviewClickSummaryResponse,
  HtmlPreviewCustomerClickSummaryResponse,
  HtmlPreviewListSnapshotPayload,
  HtmlPreviewListSnapshotResponse,
  HtmlPreviewListSummaryResponse,
} from "../types/htmlPreviewEvents";

function withClickRuntimeContext(
  payload: HtmlPreviewClickEventPayload,
): HtmlPreviewClickEventPayload {
  const iframeContext = getIframeContext();
  return {
    ...payload,
    source_id: payload.source_id || iframeContext.source || DEFAULT_SOURCE_ID,
    user_id: payload.user_id || getUserId(),
    user_name: payload.user_name || iframeContext.userName || null,
    bbk_id: payload.bbk_id || iframeContext.bbk || null,
  };
}

function withListSnapshotRuntimeContext(
  payload: HtmlPreviewListSnapshotPayload,
): HtmlPreviewListSnapshotPayload {
  const iframeContext = getIframeContext();
  return {
    ...payload,
    source_id: payload.source_id || iframeContext.source || DEFAULT_SOURCE_ID,
    bbk_id: payload.bbk_id || iframeContext.bbk || null,
  };
}

export const htmlPreviewEventsApi = {
  recordClick: async (
    payload: HtmlPreviewClickEventPayload,
  ): Promise<HtmlPreviewClickSubmitResponse> => {
    try {
      const response = await fetch(getApiUrl("/html-preview/events"), {
        method: "POST",
        headers: {
          ...buildAuthHeaders(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify(withClickRuntimeContext(payload)),
        keepalive: true,
      });
      return { success: response.ok };
    } catch (error) {
      console.warn("Failed to record HTML preview click:", error);
      return { success: false };
    }
  },
  recordListSnapshot: async (
    payload: HtmlPreviewListSnapshotPayload,
  ): Promise<HtmlPreviewListSnapshotResponse> => {
    try {
      const response = await fetch(getApiUrl("/html-preview/list-snapshot"), {
        method: "POST",
        headers: {
          ...buildAuthHeaders(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify(withListSnapshotRuntimeContext(payload)),
      });
      if (!response.ok) {
        return { success: false, customer_count: 0 };
      }
      return (await response.json()) as HtmlPreviewListSnapshotResponse;
    } catch (error) {
      console.warn("Failed to record HTML preview list snapshot:", error);
      return { success: false, customer_count: 0 };
    }
  },
  getEvents: (params?: {
    startTime?: string | null;
    endTime?: string | null;
    bbkIds?: string | null;
    cronTaskId?: string | null;
    fileUrl?: string | null;
    listKey?: string | null;
    limit?: number;
  }) => {
    const search = buildSearchParams(params);
    const query = search.toString();
    return request<HtmlPreviewClickEventListResponse>(
      `/html-preview/events${query ? `?${query}` : ""}`,
    );
  },
  getSummary: (params?: {
    startTime?: string | null;
    endTime?: string | null;
    bbkIds?: string | null;
    cronTaskId?: string | null;
    fileUrl?: string | null;
    listKey?: string | null;
    limit?: number;
  }) => {
    const search = buildSearchParams(params);
    const query = search.toString();
    return request<HtmlPreviewClickSummaryResponse>(
      `/html-preview/events/summary${query ? `?${query}` : ""}`,
    );
  },
  getCustomerSummary: (params?: {
    startTime?: string | null;
    endTime?: string | null;
    bbkIds?: string | null;
    cronTaskId?: string | null;
    fileUrl?: string | null;
    listKey?: string | null;
    limit?: number;
  }) => {
    const search = buildSearchParams(params);
    const query = search.toString();
    return request<HtmlPreviewCustomerClickSummaryResponse>(
      `/html-preview/events/customer-summary${query ? `?${query}` : ""}`,
    );
  },
  getLists: (params?: {
    startTime?: string | null;
    endTime?: string | null;
    bbkIds?: string | null;
    page?: number;
    pageSize?: number;
    limit?: number;
  }) => {
    const search = buildSearchParams(params);
    if (params?.page) {
      search.set("page", String(params.page));
    }
    if (params?.pageSize) {
      search.set("page_size", String(params.pageSize));
    }
    const query = search.toString();
    return request<HtmlPreviewListSummaryResponse>(
      `/html-preview/lists${query ? `?${query}` : ""}`,
    );
  },
  getCustomerClicks: (params?: {
    startTime?: string | null;
    endTime?: string | null;
    bbkIds?: string | null;
    cronTaskId?: string | null;
    fileUrl?: string | null;
    listKey?: string | null;
    includeUnclicked?: boolean;
    limit?: number;
  }) => {
    const search = buildSearchParams(params);
    if (params?.includeUnclicked !== undefined) {
      search.set("include_unclicked", String(params.includeUnclicked));
    }
    const query = search.toString();
    return request<HtmlPreviewCustomerClickResponse>(
      `/html-preview/customer-clicks${query ? `?${query}` : ""}`,
    );
  },
};

function buildSearchParams(params?: {
  startTime?: string | null;
  endTime?: string | null;
  bbkIds?: string | null;
  cronTaskId?: string | null;
  fileUrl?: string | null;
  listKey?: string | null;
  limit?: number;
}) {
  const search = new URLSearchParams();
  if (params?.startTime) {
    search.set("start_time", params.startTime);
  }
  if (params?.endTime) {
    search.set("end_time", params.endTime);
  }
  if (params?.bbkIds) {
    search.set("bbk_ids", params.bbkIds);
  }
  if (params?.cronTaskId) {
    search.set("cron_task_id", params.cronTaskId);
  }
  if (params?.fileUrl) {
    search.set("file_url", params.fileUrl);
  }
  if (params?.listKey) {
    search.set("list_key", params.listKey);
  }
  if (params?.limit) {
    search.set("limit", String(params.limit));
  }
  return search;
}
