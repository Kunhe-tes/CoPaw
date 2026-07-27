import { useCallback, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

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
  const blocksSubmit = open && (loading || filteredItems.length > 0);

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
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (!open || event.nativeEvent.isComposing) {
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
