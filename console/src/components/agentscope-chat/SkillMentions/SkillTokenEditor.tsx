import React, {
  forwardRef,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
} from "react";
import { SkillMentionMenu } from "./index";
import { type SkillMentionsData, useSkillMentions } from "./useSkillMentions";

interface TokenPart {
  kind: "text" | "token";
  value: string;
  selectionIndex?: number;
}

export interface SkillTokenEditorProps
  extends Omit<
    React.HTMLAttributes<HTMLDivElement>,
    "children" | "contentEditable" | "onChange" | "onInput" | "value"
  > {
  disabled?: boolean;
  placeholder?: string;
  skillMentions: SkillMentionsData;
  value: string;
  onValueChange: (value: string) => void;
}

function getTokenParts(value: string, selected: string[]): TokenPart[] {
  const parts: TokenPart[] = [];
  const tokenPattern = /@([^\s@]+)/g;
  let cursor = 0;
  let selectedIndex = 0;
  let match = tokenPattern.exec(value);

  while (match) {
    if (match.index > cursor) {
      parts.push({ kind: "text", value: value.slice(cursor, match.index) });
    }

    const name = match[1];
    if (selected[selectedIndex] === name) {
      parts.push({
        kind: "token",
        selectionIndex: selectedIndex,
        value: `@${name}`,
      });
      selectedIndex += 1;
    } else {
      parts.push({ kind: "text", value: match[0] });
    }
    cursor = match.index + match[0].length;
    match = tokenPattern.exec(value);
  }

  if (cursor < value.length || !parts.length) {
    parts.push({ kind: "text", value: value.slice(cursor) });
  }
  return parts;
}

function previousTokenAtCaret(editor: HTMLDivElement): HTMLElement | null {
  const selection = window.getSelection();
  const range = selection?.rangeCount ? selection.getRangeAt(0) : null;
  if (
    !range?.collapsed ||
    range.startContainer !== editor ||
    !range.startOffset
  ) {
    return null;
  }

  const node = editor.childNodes[range.startOffset - 1];
  return node instanceof HTMLElement && node.dataset.skillToken === "true"
    ? node
    : null;
}

function getCaretOffset(editor: HTMLDivElement): number | null {
  const selection = window.getSelection();
  const range = selection?.rangeCount ? selection.getRangeAt(0) : null;
  if (!range?.collapsed || !editor.contains(range.startContainer)) {
    return null;
  }

  const beforeCaret = range.cloneRange();
  beforeCaret.selectNodeContents(editor);
  beforeCaret.setEnd(range.startContainer, range.startOffset);
  return beforeCaret.toString().length;
}

function setCaretOffset(editor: HTMLDivElement, offset: number) {
  const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT);
  let remaining = offset;
  let node = walker.nextNode();
  while (node) {
    const text = node.textContent || "";
    if (remaining <= text.length) {
      const range = document.createRange();
      range.setStart(node, remaining);
      range.collapse(true);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
      return;
    }
    remaining -= text.length;
    node = walker.nextNode();
  }

  const range = document.createRange();
  range.selectNodeContents(editor);
  range.collapse(false);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
}

function replaceEditorContents(editor: HTMLDivElement, parts: TokenPart[]) {
  const fragment = document.createDocumentFragment();
  for (const part of parts) {
    if (part.kind === "text") {
      fragment.append(document.createTextNode(part.value));
      continue;
    }

    const token = document.createElement("span");
    token.setAttribute("aria-label", `已选技能 ${part.value}`);
    token.setAttribute("contenteditable", "false");
    token.dataset.selectionIndex = String(part.selectionIndex);
    token.dataset.skillToken = "true";
    token.style.background = "#EEF4FF";
    token.style.borderRadius = "6px";
    token.style.color = "#2957DC";
    token.style.display = "inline-block";
    token.style.fontWeight = "500";
    token.style.padding = "0 4px";
    token.textContent = part.value;
    fragment.append(token);
  }
  editor.replaceChildren(fragment);
}

export const SkillTokenEditor = forwardRef<
  HTMLDivElement,
  SkillTokenEditorProps
>(function SkillTokenEditor(
  {
    className,
    disabled = false,
    onKeyDown,
    onValueChange,
    placeholder,
    skillMentions,
    style,
    value,
    ...rest
  },
  ref,
) {
  const editorRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const placeCaretAtEndRef = useRef(false);
  const tokenParts = useMemo(
    () => getTokenParts(value, skillMentions.selected),
    [skillMentions.selected, value],
  );
  const mentions = useSkillMentions({
    ...skillMentions,
    value,
    onValueChange,
  });

  useLayoutEffect(() => {
    const editor = editorRef.current;
    if (!editor) {
      return;
    }

    const caretOffset = placeCaretAtEndRef.current
      ? value.length
      : getCaretOffset(editor);
    placeCaretAtEndRef.current = false;
    replaceEditorContents(editor, tokenParts);
    if (document.activeElement === editor) {
      setCaretOffset(editor, caretOffset ?? value.length);
    }
  }, [tokenParts, value]);

  useEffect(() => {
    if (!mentions.open) {
      return;
    }
    const closeWhenOutside = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        mentions.close();
      }
    };
    document.addEventListener("mousedown", closeWhenOutside);
    return () => document.removeEventListener("mousedown", closeWhenOutside);
  }, [mentions.close, mentions.open]);

  const removeToken = (token: HTMLElement) => {
    const selectionIndex = Number(token.dataset.selectionIndex);
    if (!Number.isInteger(selectionIndex)) {
      return;
    }
    skillMentions.onChange(
      skillMentions.selected.filter((_, index) => index !== selectionIndex),
    );
    onValueChange(
      tokenParts
        .filter((part) => part.selectionIndex !== selectionIndex)
        .map((part) => part.value)
        .join(""),
    );
  };

  return (
    <div ref={rootRef} style={{ minWidth: 0, position: "relative" }}>
      <div
        {...rest}
        ref={(node) => {
          editorRef.current = node;
          if (typeof ref === "function") {
            ref(node);
          } else if (ref) {
            ref.current = node;
          }
        }}
        aria-multiline="true"
        className={className}
        contentEditable={!disabled}
        data-placeholder={placeholder}
        role="textbox"
        suppressContentEditableWarning
        style={style}
        onInput={(event) => {
          mentions.handleInputValueChange(
            event.currentTarget.textContent || "",
          );
        }}
        onKeyDown={(event) => {
          mentions.handleKeyDown(event);
          if (event.defaultPrevented) {
            return;
          }
          if (event.key === "Backspace") {
            const token = editorRef.current
              ? previousTokenAtCaret(editorRef.current)
              : null;
            if (token) {
              event.preventDefault();
              removeToken(token);
              return;
            }
          }
          onKeyDown?.(event);
        }}
      />
      <div
        style={{
          bottom: "calc(100% + 8px)",
          left: 0,
          position: "absolute",
          right: 0,
        }}
      >
        <SkillMentionMenu
          activeIndex={mentions.activeIndex}
          error={skillMentions.error}
          items={mentions.filteredItems}
          loading={mentions.loading}
          onRetry={skillMentions.onRetry}
          open={mentions.open}
          onSelect={(item) => {
            placeCaretAtEndRef.current = true;
            mentions.select(item);
          }}
        />
      </div>
    </div>
  );
});
