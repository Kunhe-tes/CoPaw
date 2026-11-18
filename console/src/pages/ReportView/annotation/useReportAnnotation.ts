/**
 * ！！！！注意代码不同步，不能合并
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { message } from "antd";
import {
  reportAnnotationApi,
  type ModuleNote,
} from "@/api/modules/reportAnnotation";

/** 意见卡片条目 */
export interface AnnotationItem {
  /** 意见唯一标识 */
  annotationId: string;
  /** 选中元素的 HTML 字符串 */
  elementHtml: string;
  /** 意见文字内容 */
  comment: string;
  /** 创建时间戳 */
  createdAt: number;
  /** 卡片状态：编辑中 / 预览 */
  status: "editing" | "preview";
  /** 是否为本次新增（取消即删除） */
  isNew: boolean;
  /** 选中元素所属模块的 data-target-id（保存时按其聚合 moduleNoteList） */
  agentId: string;
}

/**
 * 报告意见 Hook
 */
export function useReportAnnotation(
  iframeRef: React.RefObject<HTMLIFrameElement | null>,
  options: {
    enabled: boolean;
    resultId: string | null;
    templateId: string | null;
    /** 客户 UID（保存时透传后端） */
    custUid: string;
    /** 用户 ID（保存时透传后端） */
    userId: string;
    /** 机构 ID（保存时透传后端） */
    bbkOrgId: string;
  },
) {
  const [annotationMode, setAnnotationMode] = useState(false);
  return {
    annotationMode,

  };
}