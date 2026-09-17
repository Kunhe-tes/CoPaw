/**
 * Featured Cases API module (simplified - no case_id)
 */
import { request } from "../request";
import type {
  FeaturedCase,
  FeaturedCaseCreate,
  FeaturedCaseUpdate,
  FeaturedCaseDisplay,
  FeaturedCaseListResponse,
  FeaturedCaseReorderResult,
} from "../types/featuredCases";

export const featuredCasesApi = {
  /** Get cases for current context (from X-Source-Id and X-Bbk-Id headers) */
  listCases: () => request<FeaturedCaseDisplay[]>("/featured-cases"),

  /** Get case detail by id */
  getCaseDetail: (id: number) => request<FeaturedCase>(`/featured-cases/${id}`),

  // ==================== Admin endpoints ====================

  /** Admin: list cases for current source_id context */
  adminListCases: (params: {
    bbk_id: string;
    page?: number;
    page_size?: number;
  }) => {
    const query = params
      ? new URLSearchParams(
          Object.entries(params)
            .filter(([, value]) => value !== undefined)
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : "";
    return request<FeaturedCaseListResponse>(
      `/featured-cases/admin/cases${query ? `?${query}` : ""}`,
    );
  },

  /** Admin: create case (source_id from header) */
  adminCreateCase: (caseItem: FeaturedCaseCreate) =>
    request<{ success: boolean; data: FeaturedCase }>(
      "/featured-cases/admin/cases",
      {
        method: "POST",
        body: JSON.stringify(caseItem),
      },
    ),

  /** Admin: update case */
  adminUpdateCase: (id: number, caseItem: FeaturedCaseUpdate) =>
    request<{ success: boolean; data: FeaturedCase }>(
      `/featured-cases/admin/cases/${id}`,
      {
        method: "PUT",
        body: JSON.stringify(caseItem),
      },
    ),

  /** Admin: delete case */
  adminDeleteCase: (id: number) =>
    request<{ success: boolean }>(`/featured-cases/admin/cases/${id}`, {
      method: "DELETE",
    }),

  /** Admin: atomically move a case within the current BBK queue */
  adminReorderCase: (id: number, sortOrder: number) =>
    request<{ success: boolean; data: FeaturedCaseReorderResult }>(
      `/featured-cases/admin/cases/${id}/order`,
      {
        method: "PUT",
        body: JSON.stringify({ sort_order: sortOrder }),
      },
    ),
};
