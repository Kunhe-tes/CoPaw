import React, { useEffect, useMemo, useRef, useState } from "react";
import { SparkDownloadLine } from "@agentscope-ai/icons";
import FilePreviewModal from "../FilePreviewModal";
import {
  extractDecodedFileNameFromUrl,
  getFileIcon,
  getFileType,
  isAutoPreviewHtmlLink,
  safeDecodeFileName,
} from "../FilePreviewModal/fileUtils";
import { useAutoPreviewHtml } from "../AutoPreviewHtmlContext";

export interface DownloadFileCardProps {
  url: string;
  fileName?: string;
  autoPreview?: boolean;
  enableClickTracking?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

const EMPTY = "\u00A0";

// 内联样式定义
const cardStyle: React.CSSProperties = {
  position: "relative",
  display: "flex",
  alignItems: "center",
  padding: "12px 16px",
  background: "#fff",
  border: "1px solid #d9d9d9",
  borderRadius: "8px",
  cursor: "pointer",
  transition: "all 0.3s",
  maxWidth: "280px",
  overflow: "hidden",
};

const iconStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: "24px",
  height: "24px",
  marginRight: "8px",
  flexShrink: 0,
};

const contentStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};

const nameStyle: React.CSSProperties = {
  fontSize: "14px",
  fontWeight: 500,
  color: "#262626",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const hintStyle: React.CSSProperties = {
  fontSize: "12px",
  color: "#8c8c8c",
};

const downloadBtnStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: "24px",
  height: "24px",
  background: "#1677ff",
  borderRadius: "4px",
  color: "#fff",
  cursor: "pointer",
  flexShrink: 0,
  marginLeft: "8px",
};

function DownloadFileCard(props: DownloadFileCardProps) {
  const {
    url,
    fileName: propFileName,
    autoPreview,
    enableClickTracking = false,
    className,
    style,
  } = props;
  const [previewOpen, setPreviewOpen] = useState(false);
  const autoPreviewOpenedRef = useRef(false);
  const { enabled: pageAutoPreviewEnabled, register: registerAutoPreview } =
    useAutoPreviewHtml();

  // Extract filename from URL if not provided
  const fileName = useMemo(() => {
    if (propFileName) return safeDecodeFileName(propFileName);
    return extractDecodedFileNameFromUrl(url, "未知文件");
  }, [url, propFileName]);

  const { icon } = useMemo(() => getFileIcon(fileName), [fileName]);

  // Split filename for display
  const [namePrefix, nameSuffix] = useMemo(() => {
    const match = fileName.match(/^(.*)\.[^.]+$/);
    return match ? [match[1], fileName.slice(match[1].length)] : [fileName, ""];
  }, [fileName]);

  const fileType = useMemo(() => getFileType(fileName), [fileName]);
  const shouldAutoPreview = useMemo(
    () =>
      autoPreview ??
      (pageAutoPreviewEnabled && isAutoPreviewHtmlLink(url, fileName)),
    [autoPreview, pageAutoPreviewEnabled, url, fileName],
  );
  const isAutoPreviewHtml = useMemo(
    () => isAutoPreviewHtmlLink(url, fileName),
    [fileName, url],
  );
  const shouldEnableClickTracking = enableClickTracking || isAutoPreviewHtml;

  useEffect(() => {
    if (
      !shouldAutoPreview ||
      autoPreviewOpenedRef.current ||
      fileType !== "previewable"
    ) {
      return;
    }

    if (autoPreview === undefined && pageAutoPreviewEnabled) {
      return registerAutoPreview({
        open: () => {
          autoPreviewOpenedRef.current = true;
          setPreviewOpen(true);
        },
      });
    }

    autoPreviewOpenedRef.current = true;
    setPreviewOpen(true);
  }, [
    autoPreview,
    fileType,
    pageAutoPreviewEnabled,
    registerAutoPreview,
    shouldAutoPreview,
  ]);

  const handlePreview = () => {
    setPreviewOpen(true);
  };

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation(); // 阻止事件冒泡，避免打开弹窗
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    link.target = "_blank";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // 合并样式
  const mergedCardStyle = {
    ...cardStyle,
    borderColor: "#d9d9d9",
    ...style,
  };

  const mergedHintStyle = {
    ...hintStyle,
    color: fileType === "previewable" ? "#1677ff" : "#8c8c8c",
  };

  const hintText = fileType === "previewable" ? "点击预览" : "不支持预览";

  return (
    <>
      <div
        className={className}
        style={mergedCardStyle}
        onClick={handlePreview}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            handlePreview();
          }
        }}
      >
        <div style={iconStyle}>
          {icon}
        </div>
        <div style={contentStyle}>
          <div style={nameStyle}>
            {namePrefix || EMPTY}
            {nameSuffix}
          </div>
          <div style={mergedHintStyle}>
            {hintText}
          </div>
        </div>
        {/* 直接下载按钮 */}
        <div
          style={downloadBtnStyle}
          onClick={handleDownload}
          title="下载"
        >
          <SparkDownloadLine style={{ fontSize: "14px" }} />
        </div>
      </div>
      <FilePreviewModal
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        fileUrl={url}
        fileName={fileName}
        enableClickTracking={shouldEnableClickTracking}
      />
    </>
  );
}

export default DownloadFileCard;
