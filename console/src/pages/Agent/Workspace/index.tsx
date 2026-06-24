import { useAgentsData, FileListPanel, FileEditor } from "./components";
import styles from "./index.module.less";
import {
  UploadOutlined,
  DownloadOutlined,
  SendOutlined,
} from "@ant-design/icons";
import { Button, Modal, Tooltip } from "@agentscope-ai/design";
import { workspaceApi } from "../../../api/modules/workspace";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";
import { useAppMessage } from "../../../hooks/useAppMessage";
import { getUserId, DEFAULT_USER_ID } from "../../../utils/identity";
import { useIframeStore } from "../../../stores/iframeStore";
import { TenantSelector } from "../../../components/TenantSelector";

const BROADCASTABLE_FILES = [
  "AGENTS.md",
  "BOOTSTRAP.md",
  "HEARTBEAT.md",
  "MEMORY.md",
  "PROFILE.md",
  "SOUL.md",
];

export default function WorkspacePage() {
  const { t } = useTranslation();
  const { message } = useAppMessage();
  const {
    files,
    selectedFile,
    dailyMemories,
    expandedMemory,
    fileContent,
    loading,
    workspacePath,
    hasChanges,
    enabledFiles,
    setFileContent,
    fetchFiles,
    handleFileClick,
    handleDailyMemoryClick,
    handleSave,
    handleReset,
    handleToggleFileEnabled,
    handleReorderFiles,
  } = useAgentsData();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const currentTenantId = getUserId();
  const manager = useIframeStore((state) => state.manager);
  const isDefaultUser = currentTenantId === DEFAULT_USER_ID;

  // --- File broadcast state ---
  const [selectedFileNames, setSelectedFileNames] = useState<string[]>([]);
  const [broadcastOpen, setBroadcastOpen] = useState(false);
  const [broadcastSubmitting, setBroadcastSubmitting] = useState(false);
  const [selectedTenantIds, setSelectedTenantIds] = useState<string[]>([]);

  const sanitizedSelectedTenantIds = selectedTenantIds.filter(
    (id) => id !== currentTenantId,
  );

  const handleToggleSelectedFile = (filename: string) => {
    setSelectedFileNames((current) =>
      current.includes(filename)
        ? current.filter((n) => n !== filename)
        : [...current, filename],
    );
  };

  const openBroadcastModal = () => {
    if (!selectedFileNames.length) return;
    setBroadcastOpen(true);
    setSelectedTenantIds([]);
  };

  const closeBroadcastModal = () => {
    if (broadcastSubmitting) return;
    setBroadcastOpen(false);
    setSelectedTenantIds([]);
  };

  const handleBroadcastConfirm = async () => {
    if (!selectedFileNames.length || !sanitizedSelectedTenantIds.length) return;

    setBroadcastSubmitting(true);
    try {
      const result = await workspaceApi.broadcastFiles({
        file_names: selectedFileNames,
        target_tenant_ids: sanitizedSelectedTenantIds,
        overwrite: true,
      });

      const items = Array.isArray(result.results) ? result.results : [];
      const succeeded = items.filter((item) => item.success);
      const failed = items.filter((item) => !item.success);

      if (succeeded.length > 0) {
        const lines = succeeded.map((item) => {
          const suffix = item.bootstrapped
            ? ` (${t("workspace.broadcastBootstrapped")})`
            : "";
          return `• ${item.tenant_id}${suffix}`;
        });
        message.success(
          t("workspace.broadcastSuccess", { count: succeeded.length }),
        );
        Modal.confirm({
          title: t("workspace.broadcastResultTitle"),
          content: (
            <div style={{ display: "grid", gap: 8 }}>
              <div>{t("workspace.broadcastSuccessList")}</div>
              <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {lines.join("\n")}
              </pre>
              {failed.length > 0 ? (
                <div>{t("workspace.broadcastFailureHint")}</div>
              ) : null}
            </div>
          ),
          okText: t("common.close"),
          cancelButtonProps: { style: { display: "none" } },
        });
      }

      if (failed.length > 0) {
        const failureLines = failed.map(
          (item) =>
            `• ${item.tenant_id}: ${
              item.error || t("workspace.broadcastFailed")
            }`,
        );
        if (succeeded.length === 0) {
          message.error(t("workspace.broadcastFailed"));
        }
        Modal.confirm({
          title: t("workspace.broadcastPartialFailureTitle"),
          content: (
            <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
              {failureLines.join("\n")}
            </pre>
          ),
          okText: t("common.close"),
          cancelButtonProps: { style: { display: "none" } },
        });
      }

      setBroadcastOpen(false);
      setSelectedTenantIds([]);
      setSelectedFileNames([]);
      await fetchFiles();
    } catch (error) {
      const errMsg =
        error instanceof Error ? error.message : t("workspace.broadcastFailed");
      message.error(errMsg);
    } finally {
      setBroadcastSubmitting(false);
    }
  };

  const handleDownload = async () => {
    try {
      const { blob, filename } = await workspaceApi.downloadWorkspace();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      message.success(t("workspace.downloadSuccess"));
    } catch (error) {
      console.error("Download failed:", error);
      message.error(
        t("workspace.downloadFailed") + ": " + (error as Error).message,
      );
    }
  };

  const handleFileUpload = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".zip")) {
      message.error(t("workspace.zipOnly"));
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return;
    }

    const maxSizeMb = 100;
    const maxSize = maxSizeMb * 1024 * 1024;
    if (file.size > maxSize) {
      message.error(
        t("workspace.fileSizeExceeded", {
          limit: maxSizeMb,
          size: (file.size / (1024 * 1024)).toFixed(2),
        }),
      );
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return;
    }

    try {
      const result = await workspaceApi.uploadFile(file);
      if (result.success) {
        message.success(t("workspace.uploadSuccess"));
      } else {
        message.error(t("workspace.uploadFailed") + ": " + result.message);
      }
    } catch (error) {
      console.error("Upload failed:", error);
      message.error(
        t("workspace.uploadFailed") + ": " + (error as Error).message,
      );
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  // Build enhanced files list with broadcast-selectable props
  const enhancedFiles = files.map((f) => ({
    ...f,
    selectable: BROADCASTABLE_FILES.includes(f.filename),
    broadcastSelected: selectedFileNames.includes(f.filename),
  }));

  return (
    <div className={styles.workspacePage}>
      <PageHeader
        items={[
          { title: t("nav.creationCenter") },
          { title: t("workspace.title") },
        ]}
        afterBreadcrumb={
          <p className={styles.workspacePath}>
            {t("workspace.workspacePath")}{" "}
            {workspacePath === null
              ? t("common.loading")
              : workspacePath || t("workspace.noFiles")}
          </p>
        }
        extra={
          <div className={styles.workspaceInfo}>
            <div className={styles.actionButtons}>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileUpload}
                style={{ display: "none" }}
                accept=".zip"
                title="Select a ZIP file (max 100MB)"
              />
              <Tooltip
                title={t("workspace.uploadTooltip")}
                placement="top"
                mouseEnterDelay={0.5}
              >
                <Button
                  size="small"
                  onClick={handleUploadClick}
                  icon={<UploadOutlined />}
                >
                  {t("common.upload")}
                </Button>
              </Tooltip>
              <Button
                size="small"
                onClick={handleDownload}
                icon={<DownloadOutlined />}
              >
                {t("common.download")}
              </Button>
              {selectedFileNames.length > 0 && (
                <span className={styles.selectionSummary}>
                  {t("workspace.selectedCount", {
                    count: selectedFileNames.length,
                  })}
                </span>
              )}
              <Button
                size="small"
                disabled={
                  (!isDefaultUser && !manager) || !selectedFileNames.length
                }
                icon={<SendOutlined />}
                onClick={openBroadcastModal}
              >
                {t("workspace.broadcast")}
              </Button>
            </div>
          </div>
        }
      />

      <div className={styles.content}>
        <FileListPanel
          files={enhancedFiles}
          selectedFile={selectedFile}
          dailyMemories={dailyMemories}
          expandedMemory={expandedMemory}
          workspacePath={workspacePath}
          enabledFiles={enabledFiles}
          onRefresh={fetchFiles}
          onFileClick={handleFileClick}
          onDailyMemoryClick={handleDailyMemoryClick}
          onToggleEnabled={handleToggleFileEnabled}
          onReorder={handleReorderFiles}
          onSelectToggle={handleToggleSelectedFile}
        />

        <FileEditor
          selectedFile={selectedFile}
          fileContent={fileContent}
          loading={loading}
          hasChanges={hasChanges}
          onContentChange={setFileContent}
          onSave={handleSave}
          onReset={handleReset}
        />
      </div>

      <Modal
        open={broadcastOpen}
        title={t("workspace.broadcastTitle")}
        onCancel={closeBroadcastModal}
        onOk={handleBroadcastConfirm}
        okButtonProps={{
          disabled: !sanitizedSelectedTenantIds.length,
          loading: broadcastSubmitting,
        }}
        width={640}
      >
        <div style={{ display: "grid", gap: 12 }}>
          <div style={{ color: "#666", fontSize: 12 }}>
            {t("workspace.broadcastHint")}
          </div>
          <div style={{ fontWeight: 500 }}>
            {t("workspace.broadcastCurrentSource", {
              count: selectedFileNames.length,
            })}
          </div>
          <div className={styles.distributionWarning}>
            <div>{t("workspace.broadcastDefaultAgentWarning")}</div>
            <div>{t("workspace.broadcastOverwriteWarning")}</div>
          </div>
          <TenantSelector
            selectedTenantIds={selectedTenantIds}
            onChange={(ids) =>
              setSelectedTenantIds(ids.filter((id) => id !== currentTenantId))
            }
            excludeTenantId={currentTenantId}
          />
        </div>
      </Modal>
    </div>
  );
}
