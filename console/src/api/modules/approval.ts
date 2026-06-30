import { request } from "../request";
import type { ApprovalStatusResponse } from "../types/approval";

export const approvalApi = {
  getApprovalStatus: (requestId: string) =>
    request<ApprovalStatusResponse>(
      `/approvals/${encodeURIComponent(requestId)}/status`,
    ),
};
