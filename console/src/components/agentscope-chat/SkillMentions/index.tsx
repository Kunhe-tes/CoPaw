import { ThunderboltOutlined } from "@ant-design/icons";
import { Button, Flex, Tag } from "antd";
import { useEffect, useRef } from "react";
import type { SkillMentionItem } from "./useSkillMentions";

export interface SkillMentionTagsProps {
  selected: string[];
  onRemove: (index: number) => void;
}

export function SkillMentionTags({
  selected,
  onRemove,
}: SkillMentionTagsProps) {
  if (!selected.length) {
    return null;
  }

  return (
    <Flex gap={8} wrap="wrap" style={{ marginBottom: 8 }}>
      {selected.map((name, index) => (
        <Tag key={`${name}-${index}`} closable onClose={() => onRemove(index)}>
          @{name}
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
  onSelect: (item: SkillMentionItem) => void;
  onRetry?: () => void;
}

export function SkillMentionMenu({
  activeIndex,
  error = false,
  open,
  items,
  loading = false,
  onSelect,
  onRetry,
}: SkillMentionMenuProps) {
  const activeItemRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    activeItemRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [activeIndex]);

  if (!open) {
    return null;
  }

  return (
    <Flex
      vertical
      role="listbox"
      aria-label="可用技能"
      style={{
        background: "#FFFFFF",
        borderRadius: 12,
        boxShadow: "0 14px 36px rgba(35, 31, 27, 0.12)",
        gap: 4,
        maxHeight: 420,
        overflowY: "auto",
        padding: 6,
      }}
    >
      {loading ? (
        <span role="status">加载技能中…</span>
      ) : error ? (
        <Flex align="center" gap={8} justify="space-between">
          <span role="status">加载技能失败</span>
          <Button size="small" type="text" onClick={onRetry}>
            重试
          </Button>
        </Flex>
      ) : items.length ? (
        items.map((item, index) => (
          <Button
            key={item.name}
            ref={index === activeIndex ? activeItemRef : undefined}
            block
            type="text"
            role="option"
            aria-selected={index === activeIndex}
            style={{
              alignItems: "center",
              background: index === activeIndex ? "#F3F4F6" : undefined,
              borderRadius: 8,
              display: "flex",
              height: "auto",
              minHeight: 52,
              padding: "8px 6px",
              textAlign: "left",
            }}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => onSelect(item)}
          >
            <span
              aria-hidden="true"
              style={{
                alignItems: "center",
                background: ["#EAF2FF", "#EAF8F1", "#FFF3E4", "#F5EEFF"][
                  item.name.length % 4
                ],
                borderRadius: 8,
                color: "#3769FC",
                display: "inline-flex",
                flex: "0 0 auto",
                height: 30,
                justifyContent: "center",
                marginRight: 10,
                width: 30,
              }}
            >
              <ThunderboltOutlined />
            </span>
            <span style={{ minWidth: 0 }}>
              <strong>{item.name}</strong>
              {item.description ? (
                <span style={{ color: "#6B7280", marginLeft: 8 }}>
                  {item.description}
                </span>
              ) : null}
            </span>
          </Button>
        ))
      ) : (
        <span role="status">未找到匹配的技能</span>
      )}
    </Flex>
  );
}
