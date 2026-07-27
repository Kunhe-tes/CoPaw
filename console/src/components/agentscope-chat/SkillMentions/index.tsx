import React, { useCallback, useMemo, useRef, useState } from "react";
import { Button, Flex, Tag } from "antd";

export interface SkillMentionItem {
  name: string;
  description: string;
}

export interface SkillMentionsData {
  items: SkillMentionItem[];
  selected: string[];
  loading?: boolean;
  onOpen: () => void;
  onChange: (names: string[]) => void;
}

export interface UseSkillMentionsOptions extends SkillMentionsData {
  value: string;
  onValueChange: (value: string) => void;
}

const trailingSkillMentionPattern = /(?:^|\s)@([^\s@]*)$/;
const trailingMentionTokenPattern = /@([^\s@]*)$/;

export function useSkillMentions({
  items,
  selected,
  loading = false,
  onOpen,
  onChange,
  value,
  onValueChange,
}: UseSkillMentionsOptions) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const openRef = useRef(false);

  const setMenuOpen = useCallback(
    (nextOpen: boolean) => {
      if (openRef.current === nextOpen) {
        return;
      }

      openRef.current = nextOpen;
      setOpen(nextOpen);
      if (nextOpen) {
        onOpen();
      }
    },
    [onOpen],
  );

  const filteredItems = useMemo(() => {
    const normalizedQuery = query.toLowerCase();
    return items.filter((item) =>
      item.name.toLowerCase().includes(normalizedQuery),
    );
  }, [items, query]);

  const close = useCallback(() => setMenuOpen(false), [setMenuOpen]);

  const handleInputValueChange = useCallback(
    (nextValue: string) => {
      onValueChange(nextValue);

      const match = nextValue.match(trailingSkillMentionPattern);
      if (!match) {
        setMenuOpen(false);
        return;
      }

      setQuery(match[1].toLowerCase());
      setMenuOpen(true);
    },
    [onValueChange, setMenuOpen],
  );

  const select = useCallback(
    (item: SkillMentionItem) => {
      if (loading) {
        return;
      }

      onChange([...selected, item.name]);
      onValueChange(value.replace(trailingMentionTokenPattern, " "));
      setMenuOpen(false);
    },
    [loading, onChange, onValueChange, selected, setMenuOpen, value],
  );

  const remove = useCallback(
    (index: number) => {
      onChange(selected.filter((_, itemIndex) => itemIndex !== index));
    },
    [onChange, selected],
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (!open) {
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false);
        return;
      }

      if (event.key === "Enter" && filteredItems[0] && !loading) {
        event.preventDefault();
        select(filteredItems[0]);
      }
    },
    [filteredItems, loading, open, select, setMenuOpen],
  );

  return {
    close,
    filteredItems,
    handleInputValueChange,
    handleKeyDown,
    loading,
    open,
    remove,
    select,
  };
}

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
      role="listbox"
      aria-label="可用技能"
      style={{ maxHeight: 220, overflowY: "auto", marginBottom: 8 }}
    >
      {loading ? (
        <span role="status">加载技能中…</span>
      ) : items.length ? (
        items.map((item) => (
          <div key={item.name} role="option" aria-selected={false}>
            <Button
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
          </div>
        ))
      ) : (
        <span role="status">未找到匹配的技能</span>
      )}
    </Flex>
  );
}
