import { request } from "../request";

export interface TemplateInfo {
  templateName: string;
  templateId: number;
  /** 模板标志: 'main'为普通模版，'no_query'为静态模版（无需获取数据，直接渲染） */
  templateFlag?: string;
}

export interface TemplateListResponse {
  data: TemplateInfo[];
}

export interface TemplateContentResponse {
  file_name: string;
  content: string;
}

export interface RecordDataRequest {
  resultId: string;
  templateId: string;
}

export interface RecordDataResponse {
  TRACE_ID: string;
  CRON_JOB_ID: string;
  custUid: string,
  custName: string,
  [key: string]: unknown;
}

export interface ClawFilePlanItem {
  skillId: string;
  skillName: string;
  templateId: number;
  resultId: string;
  sortOrder: number;
  key?: string;
}

export interface ClawFilePlanResponse {
  data: ClawFilePlanItem[];
}

// Dynamic Render API
export const dynamicRenderApi = {
  getTemplateList: () =>
    request<TemplateListResponse>("/template/file-templates", {
      method: "GET",
    }),

  getTemplateContent: (fileName: string) =>
    request<TemplateContentResponse>(
      `/assets/text/read?file_name=${fileName}`,
      {
        method: "GET",
      },
    ),

  getRecordData: (resultId: string, templateId: string) =>
    request<RecordDataResponse>("/template/result", {
      method: "POST",
      body: JSON.stringify({
        resultId,
        templateId: parseInt(templateId),
      }),
    }),

  getAllClawFilePlan: (params : { sapId: string; bbkOrgId: string; custUid: string }) =>
    // TODO: change api
    request<ClawFilePlanResponse>("/template/claw-file-plan", {
      method: "POST",
      body: JSON.stringify(params),
    }),
};