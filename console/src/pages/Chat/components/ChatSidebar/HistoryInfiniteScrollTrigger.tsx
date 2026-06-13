import { useEffect, useRef, type RefObject } from "react";
import { createStyles } from "antd-style";
import { DESIGN_TOKENS } from "@/config/designTokens";

const LOAD_MORE_THRESHOLD_PX = 80;

interface HistoryInfiniteScrollTriggerProps {
  scrollContainerRef: RefObject<HTMLElement | null>;
  hasMore: boolean;
  loading: boolean;
  failed: boolean;
  onLoadMore: () => void;
}

const useStyles = createStyles(({ css }) => ({
  status: css`
    margin: 8px 12px 12px;
    padding: 7px 12px;
    color: ${DESIGN_TOKENS.colorTextSecondary};
    font-size: 12px;
    text-align: center;
  `,
  retry: css`
    width: calc(100% - 24px);
    margin: 8px 12px 12px;
    padding: 7px 12px;
    border: 1px solid ${DESIGN_TOKENS.colorCardBorder};
    border-radius: 8px;
    background: transparent;
    color: ${DESIGN_TOKENS.colorTextSecondary};
    cursor: pointer;

    &:hover {
      background: rgba(55, 105, 252, 0.06);
    }
  `,
}));

export function HistoryInfiniteScrollTrigger({
  scrollContainerRef,
  hasMore,
  loading,
  failed,
  onLoadMore,
}: HistoryInfiniteScrollTriggerProps) {
  const { styles } = useStyles();
  const triggeredRef = useRef(false);
  const wasLoadingRef = useRef(loading);

  useEffect(() => {
    if (wasLoadingRef.current && !loading) {
      triggeredRef.current = false;
    }
    if (!hasMore) {
      triggeredRef.current = false;
    }
    wasLoadingRef.current = loading;
  }, [hasMore, loading]);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container || !hasMore || loading || failed) return;

    const checkForMore = () => {
      const distanceFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      if (
        container.clientHeight <= 0 ||
        distanceFromBottom > LOAD_MORE_THRESHOLD_PX ||
        triggeredRef.current
      ) {
        return;
      }

      triggeredRef.current = true;
      onLoadMore();
    };

    container.addEventListener("scroll", checkForMore, { passive: true });
    checkForMore();
    return () => container.removeEventListener("scroll", checkForMore);
  }, [failed, hasMore, loading, onLoadMore, scrollContainerRef]);

  if (!hasMore) return null;

  if (failed) {
    return (
      <button
        type="button"
        className={styles.retry}
        aria-label="重试加载历史记录"
        onClick={() => {
          triggeredRef.current = true;
          onLoadMore();
        }}
      >
        加载失败，点击重试
      </button>
    );
  }

  return (
    <div
      className={styles.status}
      role={loading ? "status" : undefined}
      aria-label={loading ? "正在加载历史记录" : undefined}
      aria-live="polite"
    >
      {loading ? "加载中..." : "滚动到底部加载更多"}
    </div>
  );
}
