import React, { useState, useCallback, useRef, useEffect } from "react";
import { Input, Upload, Tooltip, message } from "antd";
import type { GetRef, UploadFile } from "antd";
import { SparkAttachmentLine } from "@agentscope-ai/icons";
import { IconButton } from "@agentscope-ai/design";
import { Attachments } from "@/components/agentscope-chat";
import { chatApi } from "@/api/modules/chat";
import Style from "./style";
import FeaturedCases from "../FeaturedCases";
import CaseDetailDrawer from "../CaseDetailDrawer";
import { featuredCasesApi } from "@/api/modules/featuredCases";
import type { FeaturedCase } from "@/api/types/featuredCases";
import { SkillMentionMenu, SkillMentionTags } from "../SkillMentions";
import {
  useSkillMentions,
  type SkillMentionsData,
} from "../SkillMentions/useSkillMentions";
import sendIcon from "../../../assets/icons/send_highlight.svg";
import { useTranslation } from "react-i18next";

const RUNTIME_INPUT_UPLOAD_FILE_EVENT = "pasteFile";
const PLACEHOLDER_OPTIONS = [
  "告诉我你要做什么，我将召唤相应专家，为你执行...",
  "有什么要求都告诉我，我会越用越懂你...",
  "你可以给我取个名字，甚至设定我的人设...",
];

interface WelcomeCenterLayoutProps {
  greeting?: string;
  onSubmit: (data: { query: string; fileList?: UploadFile[] }) => void;
  skillMentions?: SkillMentionsData;
  beforeSubmit?: () => Promise<boolean>;
}

export default function WelcomeCenterLayout(props: WelcomeCenterLayoutProps) {
  const { greeting, onSubmit, skillMentions, beforeSubmit } = props;
  const { t } = useTranslation();
  const [inputValue, setInputValue] = useState("");
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedCase, setSelectedCase] = useState<FeaturedCase | null>(null);
  const [randomPlaceholder, setRandomPlaceholder] = useState("");
  const [loadingCase, setLoadingCase] = useState(false);
  const uploadRef = useRef<GetRef<typeof Upload>>(null);
  const inputValueRef = useRef(inputValue);
  const fileListRef = useRef(fileList);
  const isSubmittingRef = useRef(false);
  const setCurrentInputValue = useCallback((value: string) => {
    inputValueRef.current = value;
    setInputValue(value);
  }, []);
  const setCurrentFileList = useCallback(
    (
      nextFileList: UploadFile[] | ((previous: UploadFile[]) => UploadFile[]),
    ) => {
      const next =
        typeof nextFileList === "function"
          ? nextFileList(fileListRef.current)
          : nextFileList;
      fileListRef.current = next;
      setFileList(next);
    },
    [],
  );
  const skillMentionController = useSkillMentions({
    items: skillMentions?.items ?? [],
    selected: skillMentions?.selected ?? [],
    loading: skillMentions?.loading,
    onOpen: skillMentions?.onOpen ?? (() => undefined),
    onChange: skillMentions?.onChange ?? (() => undefined),
    value: inputValue,
    onValueChange: setCurrentInputValue,
  });

  // 组件挂载时随机选择placeholder文案
  useEffect(() => {
    const randomIndex = Math.floor(Math.random() * PLACEHOLDER_OPTIONS.length);
    setRandomPlaceholder(PLACEHOLDER_OPTIONS[randomIndex]);
  }, []);

  const handleSend = useCallback(async () => {
    if (isSubmittingRef.current) return;

    const submittedInputValue = inputValueRef.current;
    const query = submittedInputValue.trim();
    if (!query) return;
    const uploadedFiles = fileListRef.current.filter((file) =>
      Boolean(file.response?.url),
    );

    isSubmittingRef.current = true;
    setIsSubmitting(true);

    try {
      if (beforeSubmit && !(await beforeSubmit())) return;

      // Submit with file list
      onSubmit({ query, fileList: uploadedFiles });
      if (inputValueRef.current === submittedInputValue) {
        setCurrentInputValue("");
      }
      setCurrentFileList((currentFiles) =>
        currentFiles.filter(
          (file) => !uploadedFiles.some(({ uid }) => uid === file.uid),
        ),
      );
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }, [beforeSubmit, onSubmit, setCurrentFileList, setCurrentInputValue]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (skillMentions) {
        skillMentionController.handleKeyDown(e);
        if (e.defaultPrevented) {
          return;
        }
      }

      if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend, skillMentionController, skillMentions],
  );

  const handleFillInput = useCallback(
    (text: string) => {
      setCurrentInputValue(text);
    },
    [setCurrentInputValue],
  );

  // Handle "看案例" click - fetch detail from API
  const handleViewCase = useCallback(async (id: number) => {
    setLoadingCase(true);
    setDrawerVisible(true);
    setSelectedCase(null); // Clear previous case

    try {
      const caseData = await featuredCasesApi.getCaseDetail(id);
      setSelectedCase(caseData);
    } catch (error) {
      console.error("Failed to load case detail:", error);
      // Close drawer on error
      setDrawerVisible(false);
    } finally {
      setLoadingCase(false);
    }
  }, []);

  const handleCloseDrawer = useCallback(() => {
    setDrawerVisible(false);
    setSelectedCase(null);
  }, []);

  // Handle file upload - use chatApi to upload files (same as bottom Input)
  const handleBeforeUpload = useCallback(
    (file: File) => {
      const uid = `welcome-${Date.now()}-${Math.random()
        .toString(36)
        .slice(2)}`;
      const uploadFile: UploadFile = {
        uid,
        name: file.name,
        size: file.size,
        type: file.type,
        status: "uploading",
        percent: 0,
        originFileObj: file as UploadFile["originFileObj"],
      };

      setCurrentFileList((prev) => [...prev, uploadFile]);

      // If it's an image, generate thumbnail for preview
      if (file.type.startsWith("image/")) {
        const reader = new FileReader();
        reader.onload = (e) => {
          const dataUrl = e.target?.result;
          if (typeof dataUrl === "string") {
            setCurrentFileList((prev) =>
              prev.map((f) =>
                f.uid === uid ? { ...f, thumbUrl: dataUrl } : f,
              ),
            );
          }
        };
        reader.readAsDataURL(file);
      }

      // Actually upload the file using chatApi
      chatApi
        .uploadFile(file)
        .then((res) => {
          // Upload succeeded, update with URL
          setCurrentFileList((prev) =>
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
          // Mark as error and remove from list
          setCurrentFileList((prev) => prev.filter((f) => f.uid !== uid));
        });

      return false; // Prevent default upload behavior
    },
    [setCurrentFileList, t],
  );

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
        {/* Greeting */}
        <div className="welcome-greeting">{greeting}</div>

        {/* Input Card with upload */}
        <div className="welcome-input-card">
          {skillMentions ? (
            <SkillMentionTags
              selected={skillMentions.selected}
              onRemove={skillMentionController.remove}
            />
          ) : null}

          {skillMentions ? (
            <SkillMentionMenu
              open={skillMentionController.open}
              items={skillMentionController.filteredItems}
              loading={skillMentionController.loading}
              onSelect={skillMentionController.select}
            />
          ) : null}

          {/* Attachment preview area */}
          {fileList.length > 0 && (
            <div style={{ marginBottom: -8, marginTop: -8, marginLeft: -20 }}>
              <Attachments
                items={fileList}
                onChange={(info) => setCurrentFileList(info.fileList)}
              />
            </div>
          )}

          <Input.TextArea
            className="welcome-input-placeholder"
            value={inputValue}
            onChange={(e) => {
              if (skillMentions) {
                skillMentionController.handleInputValueChange(e.target.value);
              } else {
                setCurrentInputValue(e.target.value);
              }
            }}
            onKeyDown={handleKeyDown}
            placeholder={randomPlaceholder}
            autoSize={{ minRows: 1, maxRows: 5 }}
            bordered={false}
            disabled={isSubmitting}
          />
          <div className="welcome-input-actions">
            <div className="welcome-input-actions-left">
              <Tooltip title="上传附件">
                <div>
                  <Upload
                    ref={uploadRef}
                    showUploadList={false}
                    accept="*/*"
                    beforeUpload={handleBeforeUpload}
                  >
                    <IconButton
                      icon={<SparkAttachmentLine />}
                      bordered={false}
                    />
                  </Upload>
                </div>
              </Tooltip>
            </div>
            <button
              className="welcome-input-send-btn"
              onClick={handleSend}
              disabled={isSubmitting || !inputValue.trim()}
              type="button"
            >
              <img src={sendIcon} alt="发送" width={28} height={28} />
            </button>
          </div>
        </div>

        {/* Featured Cases */}
        <div className="welcome-cases-area">
          <FeaturedCases
            onFillInput={handleFillInput}
            onViewCase={handleViewCase}
          />
        </div>
      </div>

      {/* Case Detail Drawer */}
      <CaseDetailDrawer
        visible={drawerVisible}
        onClose={handleCloseDrawer}
        caseData={selectedCase}
        loading={loadingCase}
        onMakeSimilar={(value) => {
          setCurrentInputValue(value);
          handleCloseDrawer();
        }}
      />
    </>
  );
}
