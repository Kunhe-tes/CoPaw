/**
 * 报告意见 API 模块
 */
import { request } from "../request";

/** 模块内单条意见（对应同一 data-target-id 元素的一条意见） */
export interface ModuleNoteItem {
  /** 选中元素的 HTML 字符串 */
  originalText: string;
  /** 意见信息 */
  noteInfo: string;
}

/** 模块意见（按 data-target-id 聚合的意见列表） */
export interface ModuleNote {
  /** 元素的 data-target-id 属性值 */
  agentId: string;
  /** 该元素下的意见列表 */
  noteList: ModuleNoteItem[];
}

/** 保存报告意见请求参数 */
export interface SaveReportNoteParams {
  /** 报告结果 ID */
  resultId: string | null;
  /** 客户 UID */
  custUid: string;
  /** 用户 ID */
  userId: string;
  /** 机构 ID */
  bbkOrgId: string;
  /** 整个报告的意见（全选产生，可为空字符串） */
  fullTextNote: string;
  /** 模块意见列表（按 data-target-id 聚合） */
  moduleNoteList: ModuleNote[];
}

/** 保存报告意见响应 */
export interface SaveReportNoteResponse {
  data: unknown;
}

// Report Annotation API
export const reportAnnotationApi = {
  /**
   * 保存当前报告的意见列表
   *
   */
  saveReportNote: (params: SaveReportNoteParams) =>
    request<SaveReportNoteResponse>("/report/note/rework", {
      method: "POST",
      body: JSON.stringify(params),
    }),
};
