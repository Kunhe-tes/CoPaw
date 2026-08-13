import { createContext, useContextSelector } from "use-context-selector";
import { useMemo, useState, useCallback } from "react";

export type Locale = "cn" | "en";

// 国际化文案定义
const messages = {
  cn: {
    // Approval 相关
    "approval.title": "人工干预",
    "approval.pending": "请确认是否执行该操作",
    "approval.confirmed": "确认执行任务",
    "approval.canceled": "取消执行任务",
    "approval.cancel": "取消执行",
    "approval.confirm": "确认执行",
    "approval.taskRunning": "当前有正在执行的任务，无法发送新的任务",

    // ApprovalCancelPopover 相关
    "cancelPopover.title": "取消原因",
    "cancelPopover.placeholder": "请输入原因，以便大模型做进一步规划",
    "cancelPopover.cancel": "取消",
    "cancelPopover.confirm": "确认",
    "cancelPopover.options.notNeeded": "不需要",
    "cancelPopover.options.poorResult": "效果不理想",
    "cancelPopover.options.tooSlow": "等待时间久",
    "cancelPopover.options.wrongInput": "输入错误",

    // 通用
    "common.save": "保存",
    "common.cancel": "取消",
    "common.confirm": "确认",
    "common.delete": "删除",
    "common.edit": "编辑",
    "common.loading": "加载中...",
    "common.saveSuccess": "保存成功",
    "common.saveFailed": "保存失败",

    // Actions 相关
    "actions.regenerate": "重新生成",

    // 模型调用错误相关
    "modelCallFailed.title": "模型连接失败",
    "modelCallFailed.invalidCredential.message":
      "当前模型的访问凭证无效或已过期，暂时无法生成回复。",
    "modelCallFailed.invalidCredential.guidance":
      "请前往「设置 > 模型」检查 API Key，更新后重新发送消息。",
    "modelCallFailed.rateLimit.message":
      "模型服务请求过于频繁，暂时无法生成回复。",
    "modelCallFailed.rateLimit.guidance":
      "请稍后重新发送消息；如问题持续，请检查模型配额和服务状态。",
    "modelCallFailed.timeout.message": "模型响应超时，暂时无法生成回复。",
    "modelCallFailed.timeout.guidance":
      "请稍后重新发送消息；如问题持续，请检查模型服务状态。",
    "modelCallFailed.generic.message": "模型服务暂时无法完成请求。",
    "modelCallFailed.generic.guidance":
      "请稍后重新发送消息；如问题持续，请检查模型配置和服务状态。",
    "modelCallFailed.openSettings": "打开模型设置",
    "modelCallFailed.details": "详细报错信息",
    "modelCallFailed.copyError": "复制错误信息",
    "modelCallFailed.copied": "已复制",
    "modelCallFailed.copyFailed": "复制失败",
    "modelCallFailed.detail.httpStatus": "HTTP 状态",
    "modelCallFailed.detail.errorType": "错误类型",
    "modelCallFailed.detail.rawMessage": "原始信息",
    "modelCallFailed.detail.requestId": "请求 ID",

    // MessageImport 相关
    "messageImport.title": "Sessions 数据导入",
    "messageImport.placeholder": "输入 JSON 数据以覆盖当前 sessions",
    "messageImport.saveToLocalStorage": "保存到 LocalStorage",
  },
  en: {
    // Approval related
    "approval.title": "Human Intervention",
    "approval.pending": "Please confirm whether to execute this operation",
    "approval.confirmed": "Confirmed to execute task",
    "approval.canceled": "Canceled task execution",
    "approval.cancel": "Cancel",
    "approval.confirm": "Confirm",
    "approval.taskRunning": "A task is currently running, cannot send new task",

    // ApprovalCancelPopover related
    "cancelPopover.title": "Cancel Reason",
    "cancelPopover.placeholder":
      "Please enter the reason for better AI planning",
    "cancelPopover.cancel": "Cancel",
    "cancelPopover.confirm": "Confirm",
    "cancelPopover.options.notNeeded": "Not needed",
    "cancelPopover.options.poorResult": "Poor result",
    "cancelPopover.options.tooSlow": "Too slow",
    "cancelPopover.options.wrongInput": "Wrong input",

    // Common
    "common.save": "Save",
    "common.cancel": "Cancel",
    "common.confirm": "Confirm",
    "common.delete": "Delete",
    "common.edit": "Edit",
    "common.loading": "Loading...",
    "common.saveSuccess": "Saved successfully",
    "common.saveFailed": "Failed to save",

    // Actions related
    "actions.regenerate": "Regenerate",

    // Model call error related
    "modelCallFailed.title": "Model connection failed",
    "modelCallFailed.invalidCredential.message":
      "The current model credentials are invalid or expired, so a response could not be generated.",
    "modelCallFailed.invalidCredential.guidance":
      "Go to Settings > Models to check the API key, then send your message again.",
    "modelCallFailed.rateLimit.message":
      "The model service is receiving too many requests and cannot generate a response right now.",
    "modelCallFailed.rateLimit.guidance":
      "Send your message again later. If the issue persists, check the model quota and service status.",
    "modelCallFailed.timeout.message":
      "The model response timed out and could not be generated.",
    "modelCallFailed.timeout.guidance":
      "Send your message again later. If the issue persists, check the model service status.",
    "modelCallFailed.generic.message":
      "The model service could not complete this request.",
    "modelCallFailed.generic.guidance":
      "Send your message again later. If the issue persists, check the model configuration and service status.",
    "modelCallFailed.openSettings": "Open model settings",
    "modelCallFailed.details": "Error details",
    "modelCallFailed.copyError": "Copy error details",
    "modelCallFailed.copied": "Copied",
    "modelCallFailed.copyFailed": "Copy failed",
    "modelCallFailed.detail.httpStatus": "HTTP status",
    "modelCallFailed.detail.errorType": "Error type",
    "modelCallFailed.detail.rawMessage": "Original message",
    "modelCallFailed.detail.requestId": "Request ID",

    // MessageImport related
    "messageImport.title": "Import Sessions Data",
    "messageImport.placeholder": "Enter JSON data to override current sessions",
    "messageImport.saveToLocalStorage": "Save to LocalStorage",
  },
};

export type MessageKey = keyof typeof messages.cn;
type Messages = Record<MessageKey, string>;

export interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: MessageKey, params?: Record<string, string | number>) => string;
  messages: Messages;
}

const ChatAnywhereI18nContext = createContext<I18nContextValue | undefined>(
  undefined,
);

export function useChatAnywhereI18n<Selected>(
  selector: (value: I18nContextValue) => Selected,
): Selected {
  try {
    const context = useContextSelector(ChatAnywhereI18nContext, selector);
    return context;
  } catch {
    return {} as Selected;
  }
}

// 便捷 hook：直接获取翻译函数
export function useTranslation() {
  const t = useChatAnywhereI18n((ctx) => ctx?.t);
  const locale = useChatAnywhereI18n((ctx) => ctx?.locale);
  const setLocale = useChatAnywhereI18n((ctx) => ctx?.setLocale);
  return { t, locale, setLocale };
}

export interface ChatAnywhereI18nContextProviderProps {
  children: React.ReactNode;
  defaultLocale?: Locale;
}

export function ChatAnywhereI18nContextProvider(
  props: ChatAnywhereI18nContextProviderProps,
) {
  const { children, defaultLocale = "en" } = props;
  const [locale, setLocale] = useState<Locale>(defaultLocale);

  const t = useCallback(
    (key: MessageKey, params?: Record<string, string | number>): string => {
      let message = messages[locale][key] || key;

      // 支持参数替换，如 t('hello', { name: 'World' }) => "Hello, World"
      if (params) {
        Object.entries(params).forEach(([paramKey, value]) => {
          message = message.replace(
            new RegExp(`\\{${paramKey}\\}`, "g"),
            String(value),
          );
        });
      }

      return message;
    },
    [locale],
  );

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      t,
      messages: messages[locale],
    }),
    [locale, setLocale, t],
  );

  return (
    <ChatAnywhereI18nContext.Provider value={value}>
      {children}
    </ChatAnywhereI18nContext.Provider>
  );
}

export default ChatAnywhereI18nContext;
