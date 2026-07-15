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
    request<Record<string, unknown>>("/template/result", {
      method: "POST",
      body: JSON.stringify({
        resultId,
        templateId: parseInt(templateId),
      }),
    }),
};