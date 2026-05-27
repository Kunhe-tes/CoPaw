import { useCallback, useEffect, useRef } from "react";
import {
  useProviderContext,
  ChatInput,
  Disclaimer,
} from "@/components/agentscope-chat";
import { useChatAnywhereOptions } from "../../Context/ChatAnywhereOptionsContext";
import { useGetState } from "ahooks";
import { useChatAnywhereInput } from "../../Context/ChatAnywhereInputContext";
import { ChatAnywhereSessionsContext } from "../../Context/ChatAnywhereSessionsContext";
import useAttachments from "./useAttachments";
import { IAgentScopeRuntimeWebUIInputData } from "@/components/agentscope-chat";
import {
  RUNTIME_INPUT_SET_CONTENT_EVENT,
  type RuntimeInputRestorePayload,
} from "../hooks/followUpSubmit";
import { ChatAnywhereMessagesContext } from "../../Context/ChatAnywhereMessagesContext";
import { useContextSelector } from "use-context-selector";

const RUNTIME_INPUT_UPLOAD_FILE_EVENT = "pasteFile";

function isSubmitCancelled(result: unknown): result is {
  shouldSubmit: false;
  clearInput?: boolean;
} {
  return (
    Boolean(result) &&
    typeof result === "object" &&
    (result as { shouldSubmit?: unknown }).shouldSubmit === false
  );
}

export interface InputProps {
  onCancel: () => void;
  onSubmit: (data: IAgentScopeRuntimeWebUIInputData) => void;
}

export default function Input({ onCancel, onSubmit }: InputProps) {
  const [content, setContent, getContent] = useGetState("");
  const restoredBizParamsRef =
    useRef<IAgentScopeRuntimeWebUIInputData["biz_params"]>(undefined);
  const prefixCls = useProviderContext().getPrefixCls("chat-anywhere-input");
  const senderOptions = useChatAnywhereOptions((v) => v.sender);
  const inputContext = useChatAnywhereInput((v) => v);
  const messages = useContextSelector(
    ChatAnywhereMessagesContext,
    (v) => v.messages,
  );
  const hasMessages = messages && messages.length > 0;
  const currentSessionId = useContextSelector(
    ChatAnywhereSessionsContext,
    (v) => v.currentSessionId,
  );

  const {
    placeholder = "",
    disclaimer = "",
    maxLength,
    beforeSubmit = async () => true,
    beforeUI,
    afterUI,
    attachments,
    prefix,
    allowSpeech,
    suggestions,
  } = senderOptions || {};

  const {
    fileList,
    getFileList,
    setFileList,
    handlePasteFile,
    uploadIconButton,
    uploadFileListHeader,
  } = useAttachments(attachments, { disabled: !!inputContext.disabled });

  // Clear attachments when session changes
  useEffect(() => {
    if (setFileList) {
      setFileList([]);
    }
  }, [currentSessionId, setFileList]);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<RuntimeInputRestorePayload>).detail;
      const nextContent = detail?.content;
      if (typeof nextContent !== "string") {
        return;
      }

      setContent(nextContent);

      if (
        Object.prototype.hasOwnProperty.call(detail, "fileList") &&
        setFileList
      ) {
        setFileList(detail.fileList || []);
      }

      if (Object.prototype.hasOwnProperty.call(detail, "biz_params")) {
        restoredBizParamsRef.current = detail.biz_params;
      } else {
        restoredBizParamsRef.current = undefined;
      }
    };

    document.addEventListener(RUNTIME_INPUT_SET_CONTENT_EVENT, handler);
    return () =>
      document.removeEventListener(RUNTIME_INPUT_SET_CONTENT_EVENT, handler);
  }, [setContent, setFileList]);

  useEffect(() => {
    if (!handlePasteFile) {
      return;
    }

    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ file?: File }>).detail;
      if (detail?.file instanceof File) {
        handlePasteFile(detail.file);
      }
    };

    document.addEventListener(RUNTIME_INPUT_UPLOAD_FILE_EVENT, handler);
    return () =>
      document.removeEventListener(RUNTIME_INPUT_UPLOAD_FILE_EVENT, handler);
  }, [handlePasteFile]);

  const handleContentChange = useCallback(
    (value: string) => {
      restoredBizParamsRef.current = undefined;
      setContent(value);
    },
    [setContent],
  );

  const handleSubmit = useCallback(async () => {
    const fileList = (getFileList?.() || []).filter((i) => i.response?.url);
    const inputData: IAgentScopeRuntimeWebUIInputData = {
      query: getContent(),
      fileList,
      biz_params: restoredBizParamsRef.current,
    };
    const next = await beforeSubmit(inputData);
    if (!next) return;

    if (isSubmitCancelled(next)) {
      if (next.clearInput) {
        setContent("");
        restoredBizParamsRef.current = undefined;
        if (setFileList) {
          setFileList([]);
        }
      }
      return;
    }

    onSubmit(typeof next === "object" ? next : inputData);
    setContent("");
    restoredBizParamsRef.current = undefined;
    if (setFileList) {
      setFileList([]);
    }
  }, [
    beforeSubmit,
    getContent,
    getFileList,
    onSubmit,
    setContent,
    setFileList,
  ]);

  const handleCancel = useCallback(() => {
    onCancel();
  }, [onCancel]);

  return (
    <div className={prefixCls}>
      <div
        className={`${prefixCls}-wrapper`}
        style={{
          display: hasMessages || fileList.length > 0 ? "block" : "none",
        }}
      >
        {beforeUI}
        <ChatInput
          loading={inputContext.loading}
          disabled={inputContext.disabled}
          placeholder={placeholder}
          value={content}
          prefix={
            <>
              {uploadIconButton}
              {prefix}
            </>
          }
          header={fileList.length > 0 ? uploadFileListHeader : undefined}
          onChange={handleContentChange}
          maxLength={maxLength}
          onSubmit={handleSubmit}
          onCancel={handleCancel}
          allowSpeech={allowSpeech}
          onPasteFile={handlePasteFile}
          suggestions={suggestions}
        />
        {afterUI}
      </div>
      {disclaimer ? (
        <Disclaimer desc={disclaimer} />
      ) : (
        <div className={`${prefixCls}-blank`}></div>
      )}
    </div>
  );
}
