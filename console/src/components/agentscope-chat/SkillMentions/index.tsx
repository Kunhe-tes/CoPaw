import {
  ApiOutlined,
  FileOutlined,
  LoadingOutlined,
  SearchOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Button, Flex, Tag } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  contextReferenceText,
  type SkillMentionItem,
} from "./useSkillMentions";

export interface SkillMentionTagsProps {
  selected: SkillMentionItem[];
  onRemove: (index: number) => void;
}
export function SkillMentionTags({
  selected,
  onRemove,
}: SkillMentionTagsProps) {
  if (!selected.length) return null;
  return (
    <Flex gap={8} wrap="wrap" style={{ marginBottom: 8 }}>
      {selected.map((item, index) => (
        <Tag key={item.id} closable onClose={() => onRemove(index)}>
          {contextReferenceText(item)}
        </Tag>
      ))}
    </Flex>
  );
}

export interface SkillMentionMenuProps {
  activeIndex: number;
  open: boolean;
  items: SkillMentionItem[];
  error?: boolean;
  loading?: boolean;
  query?: string;
  onSelect: (item: SkillMentionItem) => void;
  onRetry?: () => void;
}
const groupOrder = ["skill", "mcp_tool", "workspace_file"] as const;
const groupTitles = {
  skill: "技能",
  mcp_tool: "MCP 工具",
  workspace_file: "文件",
};
function ReferenceIcon({ type }: { type: SkillMentionItem["type"] }) {
  if (type === "mcp_tool") return <ApiOutlined />;
  if (type === "workspace_file") return <FileOutlined />;
  return <ThunderboltOutlined />;
}

const LOADING_INDICATOR_DELAY_MS = 250;
const LOADING_INDICATOR_MIN_VISIBLE_MS = 150;

function useDelayedLoadingIndicator(loading: boolean) {
  const [visible, setVisible] = useState(false);
  const visibleSinceRef = useRef<number | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof window.setTimeout> | undefined;
    if (loading) {
      if (!visible) {
        timer = window.setTimeout(() => {
          visibleSinceRef.current = Date.now();
          setVisible(true);
        }, LOADING_INDICATOR_DELAY_MS);
      }
    } else if (visible) {
      const elapsed = Date.now() - (visibleSinceRef.current ?? Date.now());
      timer = window.setTimeout(
        () => {
          visibleSinceRef.current = null;
          setVisible(false);
        },
        Math.max(0, LOADING_INDICATOR_MIN_VISIBLE_MS - elapsed),
      );
    }

    return () => {
      if (timer) window.clearTimeout(timer);
    };
  }, [loading, visible]);

  return visible;
}

export function SkillMentionMenu({
  activeIndex,
  error = false,
  open,
  items,
  loading = false,
  query = "",
  onSelect,
  onRetry,
}: SkillMentionMenuProps) {
  const activeItemRef = useRef<HTMLButtonElement>(null);
  const delayedLoading = useDelayedLoadingIndicator(loading);
  useEffect(() => {
    activeItemRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [activeIndex]);
  const grouped = useMemo(
    () =>
      groupOrder
        .map((type) => ({
          type,
          items: items.filter((item) => item.type === type),
        }))
        .filter((group) => group.items.length),
    [items],
  );
  const showEmptyState = !grouped.length && (!loading || Boolean(query));
  const showLoadingIndicator =
    delayedLoading && !error && (grouped.length || !query);
  if (!open) return null;
  return (
    <Flex
      vertical
      role="listbox"
      aria-label="可用上下文引用"
      aria-busy={loading}
      style={{
        background: "#FFFFFF",
        borderRadius: 8,
        boxShadow: "0 14px 36px rgba(35, 31, 27, 0.12)",
        gap: 4,
        maxHeight: 300,
        minHeight: 64,
        overflowX: "hidden",
        overflowY: "auto",
        padding: 6,
      }}
    >
      {error ? (
        <Flex align="center" gap={8} justify="space-between">
          <span role="status">加载上下文引用失败</span>
          <Button size="small" type="text" onClick={onRetry}>
            重试
          </Button>
        </Flex>
      ) : grouped.length ? (
        grouped.map((group) => (
          <div key={group.type}>
            <div
              style={{
                color: "#8A94A6",
                fontSize: 12,
                lineHeight: "20px",
                padding: "2px 6px",
                textAlign: "left",
              }}
            >
              {groupTitles[group.type]}
            </div>
            {group.items.map((item) => {
              const index = items.indexOf(item);
              const optionId = `context-reference-option-${encodeURIComponent(
                item.id,
              )}`;
              return (
                <Button
                  key={item.id}
                  id={optionId}
                  ref={index === activeIndex ? activeItemRef : undefined}
                  block
                  type="text"
                  role="option"
                  aria-selected={index === activeIndex}
                  style={{
                    alignItems: "center",
                    background: index === activeIndex ? "#EEF4FF" : undefined,
                    borderRadius: 6,
                    display: "flex",
                    height: 40,
                    justifyContent: "flex-start",
                    minHeight: 40,
                    minWidth: 0,
                    overflow: "hidden",
                    padding: "5px 6px",
                    textAlign: "left",
                  }}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => onSelect(item)}
                >
                  <span
                    aria-hidden="true"
                    style={{
                      alignItems: "center",
                      background: "#EEF4FF",
                      borderRadius: 6,
                      color: "#3769FC",
                      display: "inline-flex",
                      flex: "0 0 auto",
                      height: 24,
                      justifyContent: "center",
                      marginRight: 8,
                      width: 24,
                    }}
                  >
                    <ReferenceIcon type={item.type} />
                  </span>
                  <span
                    style={{
                      display: "block",
                      flex: "1 1 auto",
                      minWidth: 0,
                      overflow: "hidden",
                      textAlign: "left",
                    }}
                  >
                    <strong
                      style={{
                        display: "block",
                        fontSize: 13,
                        fontWeight: 500,
                        lineHeight: "16px",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {item.type === "mcp_tool"
                        ? `${item.server} / ${item.name}`
                        : item.label}
                    </strong>
                    {item.description ? (
                      <span
                        style={{
                          color: "#6B7280",
                          display: "block",
                          fontSize: 12,
                          lineHeight: "15px",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {item.description}
                      </span>
                    ) : null}
                  </span>
                </Button>
              );
            })}
          </div>
        ))
      ) : showEmptyState ? (
        <Flex
          align="center"
          data-testid="context-reference-empty-state"
          justify="center"
          role="status"
          style={{
            color: "#7A8494",
            minHeight: 112,
            padding: "14px 10px",
            textAlign: "center",
          }}
          vertical
        >
          <SearchOutlined style={{ color: "#9AA4B2", fontSize: 18 }} />
          <strong style={{ color: "#4B5563", fontSize: 13, marginTop: 6 }}>
            未找到匹配的上下文引用
          </strong>
          <span style={{ fontSize: 12, marginTop: 2 }}>
            尝试更换关键词，或仅输入 @ 查看技能和 MCP 工具
          </span>
        </Flex>
      ) : null}
      {showLoadingIndicator ? (
        <Flex
          align="center"
          aria-label="加载上下文引用中…"
          gap={6}
          justify="center"
          role="status"
          style={{
            color: "#7A8494",
            fontSize: 12,
            minHeight: grouped.length ? 0 : 52,
            padding: grouped.length ? "4px 6px" : "12px 6px",
          }}
        >
          <LoadingOutlined />
          加载上下文引用中…
        </Flex>
      ) : null}
      {!query && !loading && !error ? (
        <span
          style={{
            color: "#8A94A6",
            fontSize: 12,
            padding: "4px 6px",
            textAlign: "left",
          }}
        >
          输入以搜索工具和文件
        </span>
      ) : null}
    </Flex>
  );
}
