import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { Input, Upload, message } from "antd";
import type { GetRef, UploadFile } from "antd";
import { SparkAttachmentLine } from "@agentscope-ai/icons";
import {
  Attachments,
  type IAgentScopeRuntimeWebUIInputData,
  type IAgentScopeRuntimeWebUISenderOptions,
} from "@/components/agentscope-chat";
import { chatApi } from "@/api/modules/chat";
import Style from "./style";
import FeaturedCases from "../FeaturedCases";
import CaseDetailDrawer from "../CaseDetailDrawer";
import { featuredCasesApi } from "@/api/modules/featuredCases";
import type { FeaturedCase } from "@/api/types/featuredCases";
import sendIcon from "../../../assets/icons/send_highlight.svg";
import { useTranslation } from "react-i18next";
import ComposerQuickMenu, {
  ComposerQuickMenuItem,
} from "@/components/agentscope-chat/ComposerQuickMenu";

const RUNTIME_INPUT_UPLOAD_FILE_EVENT = "pasteFile";
const PLACEHOLDER_OPTIONS = [
  '告诉我你要做什么，我将召唤相应专家，为你执行...',
  '有什么要求都告诉我，我会越用越懂你...',
  '你可以给我取个名字，甚至设定我的人设...'
];

interface WelcomeCenterLayoutProps {
  greeting?: string;
  placeholder?: string;
  beforeSubmit?: IAgentScopeRuntimeWebUISenderOptions["beforeSubmit"];
  quickMenuItems?: React.ReactNode | React.ReactNode[];
  onSubmit: (data: IAgentScopeRuntimeWebUIInputData) => void;
}

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

export default function WelcomeCenterLayout(props: WelcomeCenterLayoutProps) {
  const { greeting, onSubmit, beforeSubmit, placeholder, quickMenuItems } = props;
  const { t } = useTranslation();
  const [inputValue, setInputValue] = useState("");
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedCase, setSelectedCase] = useState<FeaturedCase | null>(null);
  const [randomPlaceholder, setRandomPlaceholder] = useState("");
  const [loadingCase, setLoadingCase] = useState(false);
  const uploadRef = useRef<GetRef<typeof Upload>>(null);

  useEffect(() => {
    const randomIndex = Math.floor(Math.random() * PLACEHOLDER_OPTIONS.length);
    setRandomPlaceholder(PLACEHOLDER_OPTIONS[randomIndex]);
  }, []);

  const clearComposer = useCallback(() => {
    setInputValue("");
    setFileList([]);
  }, []);

  const handleSend = useCallback(async () => {
    const trimmed = inputValue.trim();
    if (!trimmed) return;

    const uploadedFiles = fileList.filter((f) => f.response?.url);
    const inputData: IAgentScopeRuntimeWebUIInputData = {
      query: trimmed,
      fileList: uploadedFiles,
    };
    const next = beforeSubmit ? await beforeSubmit(inputData) : inputData;

    if (!next) {
      return;
    }

    if (isSubmitCancelled(next)) {
      if (next.clearInput) {
        clearComposer();
      }
      return;
    }

    onSubmit(typeof next === "object" ? next : inputData);
    clearComposer();
  }, [beforeSubmit, clearComposer, fileList, inputValue, onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleFillInput = useCallback((text: string) => {
    setInputValue(text);
  }, []);

  const handleViewCase = useCallback(async (id: number) => {
    setLoadingCase(true);
    setDrawerVisible(true);
    setSelectedCase(null);

    try {
      const caseData = await featuredCasesApi.getCaseDetail(id);
      setSelectedCase(caseData);
    } catch (error) {
      console.error("Failed to load case detail:", error);
      setDrawerVisible(false);
    } finally {
      setLoadingCase(false);
    }
  }, []);

  const handleCloseDrawer = useCallback(() => {
    setDrawerVisible(false);
    setSelectedCase(null);
  }, []);

  const handleBeforeUpload = useCallback((file: File) => {
    const uid = `welcome-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const uploadFile: UploadFile = {
      uid,
      name: file.name,
      size: file.size,
      type: file.type,
      status: "uploading",
      percent: 0,
      originFileObj: file as UploadFile["originFileObj"],
    };

    setFileList((prev) => [...prev, uploadFile]);

    if (file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const dataUrl = e.target?.result;
        if (typeof dataUrl === "string") {
          setFileList((prev) =>
            prev.map((f) =>
              f.uid === uid ? { ...f, thumbUrl: dataUrl } : f,
            ),
          );
        }
      };
      reader.readAsDataURL(file);
    }

    chatApi
      .uploadFile(file)
      .then((res) => {
        setFileList((prev) =>
          prev.map((f) =>
            f.uid === uid
              ? {
                  ...f,
                  status: "done" as const,
                  percent: 100,
                  response: { url: chatApi.filePreviewUrl(res.url) },
                }
              : f,
          ),
        );
      })
      .catch((error) => {
        console.error("File upload failed:", error);
        message.error(t("chat.attachments.uploadFailed"));
        setFileList((prev) => prev.filter((f) => f.uid !== uid));
      });

    return false;
  }, [t]);

  const mergedQuickMenuItems = useMemo(() => {
    const externalItems = React.Children.toArray(quickMenuItems).filter(Boolean);
    const uploadItem = (
      <Upload
        key="welcome-upload"
        ref={uploadRef}
        showUploadList={false}
        accept="*/*"
        beforeUpload={handleBeforeUpload}
      >
        <ComposerQuickMenuItem
          icon={<SparkAttachmentLine />}
          label={t("chat.quickMenu.upload", "上传文件")}
        />
      </Upload>
    );

    return [uploadItem, ...externalItems];
  }, [handleBeforeUpload, quickMenuItems, t]);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ file?: File }>).detail;
      if (detail?.file instanceof File) {
        handleBeforeUpload(detail.file);
      }
    };

    document.addEventListener(RUNTIME_INPUT_UPLOAD_FILE_EVENT, handler);
    return () =>
      document.removeEventListener(RUNTIME_INPUT_UPLOAD_FILE_EVENT, handler);
  }, [handleBeforeUpload]);

  return (
    <>
      <Style />
      <div className="welcome-center-layout">
        <div className="welcome-greeting">{greeting}</div>

        <div className="welcome-input-card">
          {fileList.length > 0 && (
            <div style={{ marginBottom: -8, marginTop: -8, marginLeft: -20 }}>
              <Attachments
                items={fileList}
                onChange={(info) => setFileList(info.fileList)}
              />
            </div>
          )}

          <Input.TextArea
            className="welcome-input-placeholder"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder || randomPlaceholder}
            autoSize={{ minRows: 1, maxRows: 5 }}
            bordered={false}
          />
          <div className="welcome-input-actions">
            <div className="welcome-input-actions-left">
              <ComposerQuickMenu
                triggerLabel={t("chat.quickMenu.trigger", "快捷操作")}
              >
                {mergedQuickMenuItems}
              </ComposerQuickMenu>
            </div>
            <button
              className="welcome-input-send-btn"
              onClick={handleSend}
              disabled={!inputValue.trim()}
              type="button"
            >
              <img src={sendIcon} alt="发送" width={28} height={28} />
            </button>
          </div>
        </div>

        <div className="welcome-cases-area">
          <FeaturedCases
            onFillInput={handleFillInput}
            onViewCase={handleViewCase}
          />
        </div>
      </div>

      <CaseDetailDrawer
        visible={drawerVisible}
        onClose={handleCloseDrawer}
        caseData={selectedCase}
        loading={loadingCase}
        onMakeSimilar={(value) => {
          setInputValue(value);
          handleCloseDrawer();
        }}
      />
    </>
  );
}
