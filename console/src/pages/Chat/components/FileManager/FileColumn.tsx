import { Empty, Spin, Tooltip, Typography } from "antd";
import {
  DeleteOutlined,
  FileOutlined,
  FolderOutlined,
  LinkOutlined,
  LoadingOutlined,
} from "@ant-design/icons";
import type {
  FileManagerDirectoryListing,
  FileManagerItem,
} from "@/api/modules/chat";
import { getFileIcon } from "@/components/agentscope-chat/FilePreviewModal/fileUtils";
import styles from "./index.module.less";

export interface FileColumnProps {
  column: 1 | 2 | 3;
  directory: FileManagerDirectoryListing | null;
  selectedPath: string | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  onSelect: (entry: FileManagerItem) => void;
  onDeleteDirectory?: (entry: FileManagerItem) => void;
  onLoadMore?: () => void;
}

function entryIcon(entry: FileManagerItem) {
  if (entry.kind === "directory") return <FolderOutlined />;
  if (entry.kind === "symlink") return <LinkOutlined />;
  if (entry.kind === "special") return <FileOutlined />;
  return getFileIcon(entry.name, 20).icon;
}

function formattedTime(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString();
}

export default function FileColumn({
  column,
  directory,
  selectedPath,
  loading = false,
  error,
  onRetry,
  onSelect,
  onDeleteDirectory,
  onLoadMore,
}: FileColumnProps) {
  const handleScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const element = event.currentTarget;
    if (
      directory?.next_cursor &&
      !loading &&
      element.scrollTop + element.clientHeight >= element.scrollHeight - 36
    ) {
      onLoadMore?.();
    }
  };

  return (
    <section
      className={styles.fileColumn}
      aria-label={`文件列表第 ${column} 栏`}
      onScroll={handleScroll}
    >
      {directory && (
        <header className={styles.columnHeader}>
          <span>{directory.items.length} 项</span>
        </header>
      )}

      {error ? (
        <div className={styles.statePanel}>
          <span>{error}</span>
          <button type="button" className={styles.textButton} onClick={onRetry}>
            重试
          </button>
        </div>
      ) : loading && !directory ? (
        <div className={styles.statePanel}>
          <Spin />
        </div>
      ) : directory?.items.length ? (
        <div className={styles.fileRows}>
          {directory.items.map((entry) => {
            const selected = selectedPath === entry.path;
            return (
              <div
                key={`${entry.kind}:${entry.path}`}
                className={`${styles.fileRow} ${
                  selected ? styles.selected : ""
                }`}
              >
                <button
                  type="button"
                  className={styles.entrySelect}
                  aria-pressed={selected}
                  onClick={() => onSelect(entry)}
                >
                  <span className={styles.entryIcon} aria-hidden="true">
                    {entryIcon(entry)}
                  </span>
                  <span className={styles.entryBody}>
                    <Tooltip title={entry.name} mouseEnterDelay={0.5}>
                      <Typography.Text ellipsis className={styles.entryName}>
                        {entry.name}
                      </Typography.Text>
                    </Tooltip>
                    <span className={styles.entryMeta}>
                      {entry.kind === "symlink"
                        ? "受限链接"
                        : formattedTime(entry.modified_at)}
                    </span>
                  </span>
                </button>
                {entry.kind === "directory" &&
                  entry.capabilities.archive &&
                  onDeleteDirectory && (
                    <Tooltip title="永久删除目录">
                      <button
                        type="button"
                        className={styles.deleteDirectoryButton}
                        aria-label={`永久删除目录 ${entry.name}`}
                        onClick={() => onDeleteDirectory(entry)}
                      >
                        <DeleteOutlined />
                      </button>
                    </Tooltip>
                  )}
              </div>
            );
          })}
          {loading && (
            <div className={styles.loadMore}>
              <LoadingOutlined /> 正在加载更多…
            </div>
          )}
        </div>
      ) : directory ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="此目录为空"
          className={styles.empty}
        />
      ) : (
        <div className={styles.statePanel}>选择一个目录以浏览内容</div>
      )}
    </section>
  );
}
