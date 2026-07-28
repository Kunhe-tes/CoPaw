import { useCallback, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

export interface SkillMentionItem {
  name: string;
  description: string;
}

export interface SkillMentionsData {
  items: SkillMentionItem[];
  selected: string[];
  error?: boolean;
  loading?: boolean;
  onOpen: () => void;
  onChange: (names: string[]) => void;
  onRetry?: () => void;
}

export interface UseSkillMentionsOptions extends SkillMentionsData {
  onBeforeSelect?: () => void;
  value: string;
  onValueChange: (value: string) => void;
}

const trailingSkillMentionPattern = /(?:^|\s)@([^\s@]*)$/;

interface MentionRange {
  end: number;
  start: number;
}

function getMentionRange(
  value: string,
  caretOffset: number,
): MentionRange | null {
  const textBeforeCaret = value.slice(0, caretOffset);
  const match = textBeforeCaret.match(trailingSkillMentionPattern);
  if (!match) {
    return null;
  }

  return {
    end: caretOffset,
    start: caretOffset - match[1].length - 1,
  };
}

function compareSkillNames(left: SkillMentionItem, right: SkillMentionItem) {
  return left.name.localeCompare(right.name, undefined, {
    numeric: true,
    sensitivity: "base",
  });
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
  const mentionRangeRef = useRef<MentionRange | null>(null);

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
    return items
      .filter((item) => {
        const name = item.name.toLowerCase();
        const description = item.description.toLowerCase();
        return (
          name.includes(normalizedQuery) ||
          description.includes(normalizedQuery)
        );
      })
      .sort(compareSkillNames);
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
      setQuery(nextValue.slice(range.start + 1, range.end).toLowerCase());
      setActiveIndex(0);
      setMenuOpen(true);
    },
    [onValueChange, setMenuOpen],
  );

  const select = useCallback(
    (item: SkillMentionItem) => {
      if (loading) {
        return;
      }

      const range = mentionRangeRef.current;
      if (!range) {
        return;
      }

      onBeforeSelect?.();
      onChange([...selected, item.name]);
      const trailingText = value.slice(range.end);
      const separator = /^\s/.test(trailingText) ? "" : " ";
      onValueChange(
        `${value.slice(0, range.start)}@${
          item.name
        }${separator}${trailingText}`,
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
    (index: number) => {
      onChange(selected.filter((_, itemIndex) => itemIndex !== index));
    },
    [onChange, selected],
  );

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLElement>) => {
      if (!openRef.current || event.nativeEvent.isComposing) {
        return;
      }

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

      if (event.key === "Enter" && loading) {
        event.preventDefault();
      }
    },
    [activeIndex, filteredItems, loading, open, select, setMenuOpen],
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
    remove,
    select,
  };
}
