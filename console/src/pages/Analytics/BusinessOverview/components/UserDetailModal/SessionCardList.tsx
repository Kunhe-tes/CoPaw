import { Pagination, Spin, Tooltip, message } from "antd";
import {
  AlertCircle,
  Copy,
  Layers3,
  MessageSquareText,
  PanelLeftClose,
  PanelLeftOpen,
  Radio,
  Wrench,
} from "lucide-react";
import { SessionListItem } from "../../../../../api/modules/tracing";
import { copyToClipboard } from "@/utils/clipboard";
import styles from "./index.module.less";

interface SessionCardListProps {
  sessions: SessionListItem[];
  total: number;
  page: number;
  pageSize: number;
  loading: boolean;
  selectedSessionId: string | null;
  collapsed?: boolean;
  hasErrorFilter?: boolean;
  onSelect: (sessionId: string) => void;
  onPageChange: (page: number, pageSize: number) => void;
  onToggleCollapsed?: () => void;
  onToggleErrorFilter?: () => void;
}

export default function SessionCardList({
  sessions,
  total,
  page,
  pageSize,
  loading,
  selectedSessionId,
  collapsed = false,
  hasErrorFilter = false,
  onSelect,
  onPageChange,
  onToggleCollapsed,
  onToggleErrorFilter,
}: SessionCardListProps) {
  // 格式化 Token 数量显示
  const formatTokens = (tokens: number) => {
    if (!tokens) return "0";
    if (tokens < 1000) return tokens.toString();
    if (tokens < 1000000) return `${(tokens / 1000).toFixed(1)}K`;
    return `${(tokens / 1000000).toFixed(1)}M`;
  };

  // 格式化时间显示
  const formatTime = (time: string | null) => {
    if (!time) return "-";
    return new Date(time).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const truncateText = (text: string, maxLen: number) => {
    if (text.length <= maxLen) return text;
    return text.slice(0, maxLen) + "...";
  };

  const renderTruncatedText = (text: string, maxLen: number) => {
    const truncated = truncateText(text, maxLen);
    const needTooltip = text.length > maxLen;
    if (needTooltip) {
      return (
        <Tooltip title={text} placement="topLeft">
          <span>{truncated}</span>
        </Tooltip>
      );
    }
    return <span>{truncated}</span>;
  };

  const handleCopySessionId = async (
    e: React.MouseEvent,
    sessionId: string,
  ) => {
    e.stopPropagation();
    const copied = await copyToClipboard(sessionId);
    if (copied) {
      message.success("会话 ID 已复制");
      return;
    }
    message.error("会话 ID 复制失败");
  };

  if (collapsed) {
    return (
      <div className={`${styles.sessionList} ${styles.sessionListCollapsed}`}>
        <Tooltip title="展开会话列表" placement="right">
          <button
            type="button"
            className={styles.sessionPanelToggle}
            onClick={onToggleCollapsed}
            aria-label="展开会话列表"
          >
            <PanelLeftOpen size={16} />
          </button>
        </Tooltip>
        <div className={styles.sessionCollapsedTitle}>会话列表</div>
        <div className={styles.sessionCollapsedCount}>{total}</div>
      </div>
    );
  }

  return (
    <div className={styles.sessionList}>
      <div className={styles.sessionListHeader}>
        <div className={styles.sessionListTitle}>会话列表</div>
        <div className={styles.sessionListActions}>
          {/* 报错会话筛选按钮 */}
          {onToggleErrorFilter && (
            <Tooltip
              title={hasErrorFilter ? "显示全部会话" : "筛选报错会话"}
              placement="right"
            >
              <button
                type="button"
                className={
                  hasErrorFilter
                    ? styles.errorFilterButtonActive
                    : styles.errorFilterButton
                }
                onClick={onToggleErrorFilter}
                aria-label={hasErrorFilter ? "显示全部会话" : "筛选报错会话"}
              >
                <AlertCircle size={16} />
              </button>
            </Tooltip>
          )}
          {/* 收起会话列表按钮 */}
          <Tooltip title="收起会话列表" placement="right">
            <button
              type="button"
              className={styles.sessionPanelToggle}
              onClick={onToggleCollapsed}
            aria-label="收起会话列表"
          >
            <PanelLeftClose size={16} />
          </button>
        </Tooltip>
        </div>
      </div>

      {loading ? (
        <div className={styles.sessionLoading}>
          <Spin size="small" />
        </div>
      ) : sessions.length === 0 ? (
        <div className={styles.sessionEmpty}>暂无会话数据</div>
      ) : (
        <>
          <div className={styles.sessionCards}>
            {sessions.map((session) => {
              const selected = selectedSessionId === session.session_id;
              const sessionTitle = session.session_name || "未命名会话";

              return (
                <div
                  key={session.session_id}
                  className={`${styles.sessionCard} ${
                    selected ? styles.selected : ""
                  }`}
                  onClick={() => onSelect(session.session_id)}
                >
                  <div className={styles.sessionCardHeader}>
                    <div className={styles.sessionTitleBlock}>
                      <div className={styles.sessionName}>
                        {renderTruncatedText(sessionTitle, 18)}
                      </div>
                      <div className={styles.sessionIdRow}>
                        <span className={styles.sessionId}>
                          {renderTruncatedText(session.session_id, 42)}
                        </span>
                        <Tooltip title="复制会话 ID">
                          <button
                            type="button"
                            className={styles.copyButton}
                            aria-label="复制会话 ID"
                            onClick={(e) =>
                              handleCopySessionId(e, session.session_id)
                            }
                          >
                            <Copy size={13} />
                          </button>
                        </Tooltip>
                      </div>
                    </div>
                    {selected && (
                      <span className={styles.sessionSelectedBadge}>当前</span>
                    )}
                  </div>

                  <div className={styles.sessionMetricGrid}>
                    <div className={styles.sessionMetric}>
                      <MessageSquareText size={14} />
                      <span>对话</span>
                      <strong>{session.total_traces}</strong>
                    </div>
                    <div className={styles.sessionMetric}>
                      <Layers3 size={14} />
                      <span>Token</span>
                      <strong>{formatTokens(session.total_tokens)}</strong>
                    </div>
                    <div className={styles.sessionMetric}>
                      <Wrench size={14} />
                      <span>技能</span>
                      <strong>{session.total_skills}</strong>
                    </div>
                  </div>

                  <div className={styles.sessionFooter}>
                    <span className={styles.sessionChannel}>
                      <Radio size={12} />
                      {session.channel || "-"}
                    </span>
                    <span className={styles.sessionTime}>
                      {formatTime(session.last_active)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {total > pageSize && (
            <div className={styles.sessionPagination}>
              <Pagination
                simple
                current={page}
                pageSize={pageSize}
                showSizeChanger
                pageSizeOptions={["10", "20", "50", "100"]}
                total={total}
                onChange={onPageChange}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
