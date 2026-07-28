import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

export type ContextReferenceType = "skill" | "mcp_tool" | "workspace_file";

export interface SkillMentionItem {
  id: string;
  type: ContextReferenceType;
  label: string;
  description: string;
  name?: string;
  server?: string;
  root?: "media" | "static";
  relative_path?: string;
}

export interface SkillMentionsData {
  items: SkillMentionItem[];
  selected: SkillMentionItem[];
  error?: boolean;
  loading?: boolean;
  onOpen: (query: string) => void;
  onChange: (items: SkillMentionItem[]) => void;
  onRetry?: () => void;
}

export interface UseSkillMentionsOptions extends SkillMentionsData {
  onBeforeSelect?: () => void;
  value: string;
  onValueChange: (value: string) => void;
}

const trailingSkillMentionPattern = /(?:^|\s)@([^@]*)$/;

interface MentionRange {
  end: number;
  start: number;
}

export function contextReferenceText(item: SkillMentionItem) {
  if (item.type === "mcp_tool") return `@${item.server}/${item.name}`;
  return `@${item.name || item.label}`;
}

function getMentionRange(
  value: string,
  caretOffset: number,
): MentionRange | null {
  const match = value.slice(0, caretOffset).match(trailingSkillMentionPattern);
  return match
    ? { end: caretOffset, start: caretOffset - match[1].length - 1 }
    : null;
}

export function useSkillMentions({
  items,
  selected,
  loading = false,
  onOpen,
  onChange,
  onBeforeSelect,
  value,
  onValueChange,
}: UseSkillMentionsOptions) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const openRef = useRef(false);
  const requestedQueryRef = useRef<string | null>(null);
  const mentionRangeRef = useRef<MentionRange | null>(null);

  const setMenuOpen = useCallback(
    (nextOpen: boolean) => {
      if (openRef.current === nextOpen) return;
      openRef.current = nextOpen;
      setOpen(nextOpen);
      if (nextOpen) {
        requestedQueryRef.current = "";
        onOpen("");
      }
    },
    [onOpen],
  );

  useEffect(() => {
    if (!open) return;
    if (requestedQueryRef.current === query) return;
    if (!query) {
      requestedQueryRef.current = "";
      onOpen("");
      return;
    }
    const timer = window.setTimeout(() => {
      requestedQueryRef.current = query;
      onOpen(query);
    }, 200);
    return () => window.clearTimeout(timer);
  }, [onOpen, open, query]);

  const filteredItems = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return items;
    return items.filter((item) => {
      const values =
        item.type === "workspace_file"
          ? [item.label]
          : [item.label, item.description, item.name, item.server];
      return values.some(
        (value) => value?.toLocaleLowerCase().includes(needle),
      );
    });
  }, [items, query]);
  const blocksSubmit = open && (loading || filteredItems.length > 0);
  const close = useCallback(() => setMenuOpen(false), [setMenuOpen]);

  const handleInputValueChange = useCallback(
    (nextValue: string, caretOffset = nextValue.length) => {
      onValueChange(nextValue);
      const range = getMentionRange(nextValue, caretOffset);
      if (!range) {
        mentionRangeRef.current = null;
        setMenuOpen(false);
        return;
      }
      mentionRangeRef.current = range;
      setQuery(nextValue.slice(range.start + 1, range.end));
      setActiveIndex(0);
      setMenuOpen(true);
    },
    [onValueChange, setMenuOpen],
  );

  const select = useCallback(
    (item: SkillMentionItem) => {
      if (
        loading ||
        !mentionRangeRef.current ||
        selected.some((entry) => entry.id === item.id)
      )
        return;
      const range = mentionRangeRef.current;
      onBeforeSelect?.();
      onChange([...selected, item]);
      const trailingText = value.slice(range.end);
      const separator = /^\s/.test(trailingText) ? "" : " ";
      onValueChange(
        `${value.slice(0, range.start)}${contextReferenceText(
          item,
        )}${separator}${trailingText}`,
      );
      setMenuOpen(false);
    },
    [
      loading,
      onBeforeSelect,
      onChange,
      onValueChange,
      selected,
      setMenuOpen,
      value,
    ],
  );

  const remove = useCallback(
    (index: number) =>
      onChange(selected.filter((_, itemIndex) => itemIndex !== index)),
    [onChange, selected],
  );
  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLElement>) => {
      if (!openRef.current || event.nativeEvent.isComposing) return;
      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false);
        return;
      }
      if (event.key === "ArrowDown" && filteredItems.length) {
        event.preventDefault();
        setActiveIndex((current) =>
          Math.min(current + 1, filteredItems.length - 1),
        );
        return;
      }
      if (event.key === "ArrowUp" && filteredItems.length) {
        event.preventDefault();
        setActiveIndex((current) => Math.max(current - 1, 0));
        return;
      }
      if (event.key === "Enter" && filteredItems[activeIndex] && !loading) {
        event.preventDefault();
        select(filteredItems[activeIndex]);
        return;
      }
      if (event.key === "Enter" && loading) event.preventDefault();
    },
    [activeIndex, filteredItems, loading, select, setMenuOpen],
  );

  return {
    activeIndex,
    blocksSubmit,
    close,
    filteredItems,
    handleInputValueChange,
    handleKeyDown,
    loading,
    open,
    query,
    remove,
    select,
  };
}
