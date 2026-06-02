import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Modal, message, Tooltip, Spin } from "antd";
import { FullscreenOutlined } from "@ant-design/icons";
import {
  SparkFalseLine,
  SparkDownloadLine,
  // SparkCopyLine,
  // SparkTrueLine,
} from "@agentscope-ai/icons";
import { IconButton } from "@agentscope-ai/design";
import { getFileIcon, getFileType, getContentType } from "./fileUtils";
import Markdown from "../Markdown";
import { htmlPreviewEventsApi } from "@/api/modules/htmlPreviewEvents";
import { useHtmlPreviewTracking } from "../HtmlPreviewTrackingContext";
import { attachHtmlPreviewClickTracker } from "./htmlPreviewClickTracking";

export interface FilePreviewModalProps {
  open: boolean;
  onClose: () => void;
  fileUrl: string;
  fileName: string;
  enableClickTracking?: boolean;
}

function FilePreviewModal(props: FilePreviewModalProps) {
  const { open, onClose, fileUrl, fileName, enableClickTracking = false } =
    props;
  const [copied, setCopied] = useState(false);
  const [fullscreen, setFullscreen] = useState(true);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [markdownContent, setMarkdownContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const cleanupClickTrackingRef = useRef<(() => void) | null>(null);
  const trackingContext = useHtmlPreviewTracking();
  const fileType = useMemo(() => getFileType(fileName), [fileName]);
  const isMarkdownFile = useMemo(() => /\.mdx?$/i.test(fileName), [fileName]);
  const { icon, color } = useMemo(() => getFileIcon(fileName, 48), [fileName]);
  const isHtmlPreview = useMemo(
    () => fileType === "previewable" && getContentType(fileName) === "text/html",
    [fileName, fileType],
  );

  // fetch 文件数据并创建 Blob URL
  useEffect(() => {
    if (open && fileType === "previewable" && fileUrl) {
      setLoading(true);
      setError(null);
      setBlobUrl(null);
      setMarkdownContent(null);

      fetch(fileUrl)
        .then(async (res) => {
          if (!res.ok) throw new Error("加载失败");

          if (isMarkdownFile) {
            setMarkdownContent(await res.text());
            return;
          }

          const blob = await res.blob();
          const contentType = getContentType(fileName);
          const newBlob = new Blob([blob], { type: contentType });
          const url = URL.createObjectURL(newBlob);
          setBlobUrl(url);
        })
        .catch(() => {
          setError("文件暂时无法预览");
        })
        .finally(() => {
          setLoading(false);
        });
    }
  }, [open, fileType, fileUrl, fileName, isMarkdownFile]);

  // 清理 Blob URL
  useEffect(() => {
    return () => {
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  }, [blobUrl]);

  useEffect(() => {
    if (!open) {
      cleanupClickTrackingRef.current?.();
      cleanupClickTrackingRef.current = null;
    }
  }, [open]);

  useEffect(() => {
    return () => {
      cleanupClickTrackingRef.current?.();
      cleanupClickTrackingRef.current = null;
    };
  }, []);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(fileUrl);
      message.success("链接已复制");
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      message.error("复制失败");
    }
  }, [fileUrl]);

  const handleDownload = useCallback(() => {
    const link = document.createElement("a");
    link.href = fileUrl;
    link.download = fileName;
    link.target = "_blank";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, [fileUrl, fileName]);

  const handleFullscreen = useCallback(() => {
    setFullscreen((prev) => !prev);
  }, []);

  const handleIframeLoad = useCallback(() => {
    cleanupClickTrackingRef.current?.();
    cleanupClickTrackingRef.current = null;

    const iframe = iframeRef.current;
    if (!iframe || !isHtmlPreview || !enableClickTracking) {
      return;
    }

    try {
      cleanupClickTrackingRef.current = attachHtmlPreviewClickTracker({
        iframe,
        metadata: {
          cronTaskId: trackingContext.cronTaskId,
          cronTaskName: trackingContext.cronTaskName,
          fileUrl,
          fileName,
        },
        reporter: htmlPreviewEventsApi.recordClick,
        listSnapshotReporter: htmlPreviewEventsApi.recordListSnapshot,
      });
    } catch (error) {
      console.warn("Failed to attach HTML preview click tracker:", error);
    }
  }, [
    enableClickTracking,
    fileName,
    fileUrl,
    isHtmlPreview,
    trackingContext,
  ]);

  const previewHeight = fullscreen ? "85vh" : "500px";

  const renderPreviewContent = useMemo(() => {
    if (fileType === "previewable") {
      if (loading) {
        return <Spin tip="加载中..." />;
      }
      if (error) {
        return (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "24px" }}>
            <div style={{ color: "#8c8c8c", marginBottom: "16px", fontSize: "14px" }}>
              {error}
            </div>
            <IconButton icon={<SparkDownloadLine />} onClick={handleDownload}>
              下载文件查看
            </IconButton>
          </div>
        );
      }
      if (isMarkdownFile && markdownContent !== null) {
        return (
          <div style={{ width: "100%", height: previewHeight, overflow: "auto", padding: "16px", boxSizing: "border-box", textAlign: "left" }}>
            <Markdown content={markdownContent} />
          </div>
        );
      }
      if (blobUrl) {
        return (
          <div style={{ width: "100%", height: previewHeight }}>
            <iframe
              ref={iframeRef}
              src={blobUrl}
              style={{ width: "100%", height: "100%", border: "none" }}
              title="File Preview"
              onLoad={handleIframeLoad}
            />
          </div>
        );
      }
      return null;
    }

    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "24px", textAlign: "center" }}>
        <div style={{ marginBottom: "16px", color }}>
          {icon}
        </div>
        <div style={{ fontSize: "16px", fontWeight: 500, marginBottom: "8px", maxWidth: "300px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {fileName}
        </div>
        <div style={{ fontSize: "12px", color: "#8c8c8c", marginBottom: "16px" }}>
          该文件类型不支持预览
        </div>
        <IconButton
          icon={<SparkDownloadLine />}
          onClick={handleDownload}
        >
          下载文件
        </IconButton>
      </div>
    );
  }, [
    fileType,
    loading,
    error,
    isMarkdownFile,
    markdownContent,
    previewHeight,
    blobUrl,
    fileName,
    icon,
    color,
    handleDownload,
    handleIframeLoad,
  ]);

  const headerActions = useMemo(() => {
    const actions = [
      // <Tooltip key="copy" title="复制链接">
      //   <IconButton
      //     size="small"
      //     icon={copied ? <SparkTrueLine style={{ color: "#52c41a" }} /> : <SparkCopyLine />}
      //     onClick={handleCopy}
      //     bordered={false}
      //   />
      // </Tooltip>,
      <Tooltip key="download" title="下载文件">
        <IconButton
          size="small"
          icon={<SparkDownloadLine />}
          onClick={handleDownload}
          bordered={false}
        />
      </Tooltip>,
    ];

    if (fileType === "previewable") {
      actions.unshift(
        <Tooltip key="fullscreen" title={fullscreen ? "退出全屏" : "全屏预览"}>
          <IconButton
            size="small"
            icon={<FullscreenOutlined />}
            onClick={handleFullscreen}
            bordered={false}
          />
        </Tooltip>,
      );
    }

    return actions;
  }, [fileType, handleCopy, handleDownload, handleFullscreen, copied, fullscreen]);

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={fullscreen ? "95vw" : 800}
      centered
      closeIcon={
        <IconButton
          size="small"
          icon={<SparkFalseLine />}
          bordered={false}
        />
      }
      title={
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}>
          <span style={{ fontSize: "14px", fontWeight: 500, maxWidth: fullscreen ? "60vw" : "400px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {fileName}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", marginRight: "32px" }}>
            {headerActions}
          </div>
        </div>
      }
      styles={{
        content: { padding: "16px 24px" },
        body: { padding: "16px 0" },
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: fullscreen ? "85vh" : "200px" }}>
        {renderPreviewContent}
      </div>
    </Modal>
  );
}

export default FilePreviewModal;
