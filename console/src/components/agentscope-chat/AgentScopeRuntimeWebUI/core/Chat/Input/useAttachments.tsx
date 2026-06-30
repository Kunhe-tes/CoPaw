import { IAgentScopeRuntimeWebUISenderAttachmentsOptions } from "@/components/agentscope-chat";
import { Upload } from "antd";
import type { UploadFile } from "antd";
import { IconButton } from "@agentscope-ai/design";
import { SparkAttachmentLine } from "@agentscope-ai/icons";
import { Sender, Attachments } from "@/components/agentscope-chat";
import React, { useCallback, useRef, useState } from "react";

export default function useAttachments(
  attachments: IAgentScopeRuntimeWebUISenderAttachmentsOptions,
  options?: {
    disabled?: boolean;
  },
) {
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const fileListRef = useRef<UploadFile[]>([]);
  fileListRef.current = fileList;

  const getFileList = useCallback(() => fileListRef.current, []);

  const { trigger, customRequest, maxCount, ...rest } = attachments || {};
  const uidCounter = useRef(0);

  const handlePasteFile = useCallback(
    (file: File) => {
      if (!customRequest) return;

      const fileType = file.type || "";
      const fileName = file.name || "";

      if (maxCount && fileListRef.current.length >= maxCount) return;

      const getExtension = () => {
        const nameMatch = fileName.match(/\.([^.]+)$/);
        if (nameMatch) return nameMatch[1].toLowerCase();
        const typeMatch = fileType.match(/\/([^/+]+)/);
        return typeMatch ? typeMatch[1].toLowerCase() : "bin";
      };

      const uid = `paste-${Date.now()}-${uidCounter.current++}`;
      const uploadFile: UploadFile = {
        uid,
        name: fileName || `pasted-${Date.now()}.${getExtension()}`,
        size: file.size,
        type: fileType,
        status: "uploading",
        percent: 0,
        originFileObj: file as UploadFile["originFileObj"],
      };

      setFileList((prev) => [...prev, uploadFile]);

      if (fileType.startsWith("image/")) {
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

      customRequest(
        {
          file,
          filename: "file",
          action: "",
          method: "POST",
          onSuccess: (response) => {
            setFileList((prev) =>
              prev.map((f) =>
                f.uid === uid
                  ? { ...f, status: "done" as const, response, percent: 100 }
                  : f,
              ),
            );
          },
          onError: (error) => {
            setFileList((prev) =>
              prev.map((f) =>
                f.uid === uid ? { ...f, status: "error" as const, error } : f,
              ),
            );
          },
          onProgress: (event) => {
            setFileList((prev) =>
              prev.map((f) =>
                f.uid === uid ? { ...f, percent: event?.percent } : f,
              ),
            );
          },
        },
        { defaultRequest: () => undefined },
      );
    },
    [customRequest, maxCount],
  );

  if (customRequest) {
    const uploadIconButton = (
      <Upload
        fileList={fileList}
        showUploadList={false}
        onChange={(info) => {
          setFileList(info.fileList);
        }}
        {...rest}
        customRequest={customRequest}
        maxCount={maxCount}
        disabled={options?.disabled}
      >
        {trigger ? (
          React.createElement(trigger, { disabled: options?.disabled })
        ) : (
          <IconButton
            disabled={options?.disabled}
            icon={<SparkAttachmentLine />}
            bordered={false}
          />
        )}
      </Upload>
    );

    const uploadFileListHeader = (
      <Sender.Header closable={false} open={fileList?.length > 0}>
        <Attachments
          items={fileList}
          onChange={(info) => setFileList(info.fileList)}
        />
      </Sender.Header>
    );

    return {
      fileList,
      getFileList,
      setFileList,
      handlePasteFile,
      uploadIconButton,
      uploadFileListHeader,
    };
  } else {
    return {
      enabled: false,
      handlePasteFile: undefined,
    };
  }
}
