import { Button, Flex, Tag } from "antd";
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
  open: boolean;
  items: SkillMentionItem[];
  loading?: boolean;
  onSelect: (item: SkillMentionItem) => void;
}

export function SkillMentionMenu({
  open,
  items,
  loading = false,
  onSelect,
}: SkillMentionMenuProps) {
  if (!open) {
    return null;
  }

  return (
    <Flex
      vertical
      role="group"
      aria-label="可用技能"
      style={{ maxHeight: 220, overflowY: "auto", marginBottom: 8 }}
    >
      {loading ? (
        <span role="status">加载技能中…</span>
      ) : items.length ? (
        items.map((item) => (
          <Button
            key={item.name}
            block
            type="text"
            style={{ height: "auto", padding: "6px 8px", textAlign: "left" }}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => onSelect(item)}
          >
            <strong>{item.name}</strong>
            {item.description ? (
              <span style={{ color: "#4B5563", display: "block" }}>
                {item.description}
              </span>
            ) : null}
          </Button>
        ))
      ) : (
        <span role="status">未找到匹配的技能</span>
      )}
    </Flex>
  );
}
