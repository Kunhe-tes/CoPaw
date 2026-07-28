import React, {
  forwardRef,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { SkillMentionMenu } from "./index";
import {
  contextReferenceText,
  type SkillMentionItem,
  type SkillMentionsData,
  useSkillMentions,
} from "./useSkillMentions";

interface TokenPart {
  kind: "text" | "token";
  referenceType?: SkillMentionItem["type"];
  value: string;
  selectionIndex?: number;
}

const tokenIcons = {
  mcp_tool: {
    label: "MCP 工具",
    path: "M5 2.5a2.5 2.5 0 0 0 0 5h6a2.5 2.5 0 1 1 0 5H5a2.5 2.5 0 1 1 0-5h6a2.5 2.5 0 1 0 0-5z",
  },
  skill: { label: "技能", path: "M9.3 1 2.7 9H7l-1.2 6 7.5-9H9z" },
  workspace_file: { label: "文件", path: "M4 1.5h5l3 3v10H4zM9 1.5v3h3" },
} as const;

export interface SkillTokenEditorProps
  extends Omit<
    React.HTMLAttributes<HTMLDivElement>,
    "children" | "contentEditable" | "onChange" | "onInput" | "value"
  > {
  disabled?: boolean;
  readOnly?: boolean;
  placeholder?: string;
  skillMentions: SkillMentionsData;
  value: string;
  onValueChange: (value: string) => void;
}

function getTokenParts(
  value: string,
  selected: SkillMentionItem[],
): TokenPart[] {
  const parts: TokenPart[] = [];
  let cursor = 0;
  const usedSelectionIndexes = new Set<number>();
  while (true) {
    let selectedIndex = -1;
    let tokenIndex = Number.POSITIVE_INFINITY;
    selected.forEach((item, index) => {
      if (usedSelectionIndexes.has(index)) return;
      const tokenText = contextReferenceText(item);
      const candidate = value.indexOf(tokenText, cursor);
      const candidateEnd = candidate + tokenText.length;
      if (
        candidate >= 0 &&
        (!value[candidateEnd] || /\s/.test(value[candidateEnd])) &&
        candidate < tokenIndex
      ) {
        selectedIndex = index;
        tokenIndex = candidate;
      }
    });
    if (selectedIndex < 0) break;
    const tokenText = contextReferenceText(selected[selectedIndex]);
    const tokenEnd = tokenIndex + tokenText.length;
    if (tokenIndex > cursor) {
      parts.push({ kind: "text", value: value.slice(cursor, tokenIndex) });
    }
    parts.push({
      kind: "token",
      selectionIndex: selectedIndex,
      referenceType: selected[selectedIndex].type,
      value: tokenText,
    });
    usedSelectionIndexes.add(selectedIndex);
    cursor = tokenEnd;
  }

  if (cursor < value.length || !parts.length) {
    parts.push({ kind: "text", value: value.slice(cursor) });
  }
  return parts;
}

function previousTokenAtCaret(editor: HTMLDivElement): HTMLElement | null {
  const selection = window.getSelection();
  const range = selection?.rangeCount ? selection.getRangeAt(0) : null;
  if (!range?.collapsed) {
    return null;
  }

  let node: ChildNode | null = null;
  if (range.startContainer === editor && range.startOffset > 0) {
    node = editor.childNodes[range.startOffset - 1];
  } else if (
    range.startContainer.nodeType === Node.TEXT_NODE &&
    range.startOffset <= 1 &&
    /^\s*$/.test(
      (range.startContainer.textContent || "").slice(0, range.startOffset),
    )
  ) {
    node = range.startContainer.previousSibling;
  }
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
    token.setAttribute("aria-label", `已选上下文引用 ${part.value}`);
    token.setAttribute("contenteditable", "false");
    token.dataset.selectionIndex = String(part.selectionIndex);
    token.dataset.skillToken = "true";
    token.dataset.referenceType = part.referenceType || "skill";
    token.style.background = "#EEF4FF";
    token.style.borderRadius = "6px";
    token.style.color = "#2957DC";
    token.style.display = "inline-block";
    token.style.fontWeight = "500";
    token.style.padding = "0 4px";
    const icon = document.createElement("span");
    const iconDetails = tokenIcons[part.referenceType || "skill"];
    icon.setAttribute("aria-label", iconDetails.label);
    icon.setAttribute("role", "img");
    icon.style.color =
      part.referenceType === "mcp_tool"
        ? "#2F7D5B"
        : part.referenceType === "workspace_file"
        ? "#A56A24"
        : "#3769FC";
    icon.style.display = "inline-flex";
    icon.style.height = "11px";
    icon.style.marginRight = "3px";
    icon.style.width = "11px";
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("fill", "none");
    svg.setAttribute("height", "11");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("stroke-width", "1.5");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("width", "11");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", iconDetails.path);
    svg.append(path);
    icon.append(svg);
    token.append(icon, document.createTextNode(part.value));
    fragment.append(token);
  }
  editor.replaceChildren(fragment);
}

function selectedReferencesVisibleInEditor(
  editor: HTMLDivElement,
  selected: SkillMentionItem[],
): SkillMentionItem[] {
  return Array.from(editor.querySelectorAll<HTMLElement>("[data-skill-token]"))
    .map((token) => Number(token.dataset.selectionIndex))
    .filter(Number.isInteger)
    .map((index) => selected[index])
    .filter((item): item is SkillMentionItem => Boolean(item));
}

export const SkillTokenEditor = forwardRef<
  HTMLDivElement,
  SkillTokenEditorProps
>(function SkillTokenEditor(
  {
    className,
    disabled = false,
    onKeyDown,
    onCompositionEnd,
    onCompositionStart,
    onValueChange,
    placeholder,
    readOnly = false,
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
  const isComposingRef = useRef(false);
  const [compositionVersion, setCompositionVersion] = useState(0);
  const tokenParts = useMemo(
    () => getTokenParts(value, skillMentions.selected),
    [skillMentions.selected, value],
  );
  const mentions = useSkillMentions({
    ...skillMentions,
    onBeforeSelect: () => {
      placeCaretAtEndRef.current = true;
    },
    value,
    onValueChange,
  });
  const closeMentionMenu = mentions.close;
  const mentionMenuOpen = mentions.open;

  useLayoutEffect(() => {
    const editor = editorRef.current;
    if (!editor || isComposingRef.current) {
      return;
    }

    const shouldPlaceCaretAtEnd = placeCaretAtEndRef.current;
    const caretOffset = shouldPlaceCaretAtEnd
      ? value.length
      : getCaretOffset(editor);
    placeCaretAtEndRef.current = false;
    replaceEditorContents(editor, tokenParts);
    if (shouldPlaceCaretAtEnd) {
      editor.focus({ preventScroll: true });
    }
    if (shouldPlaceCaretAtEnd || document.activeElement === editor) {
      setCaretOffset(editor, caretOffset ?? value.length);
    }
  }, [compositionVersion, tokenParts, value]);

  useEffect(() => {
    if (!mentionMenuOpen) {
      return;
    }
    const closeWhenOutside = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        closeMentionMenu();
      }
    };
    document.addEventListener("mousedown", closeWhenOutside);
    return () => document.removeEventListener("mousedown", closeWhenOutside);
  }, [closeMentionMenu, mentionMenuOpen]);

  const removeToken = (token: HTMLElement) => {
    const selectionIndex = Number(token.dataset.selectionIndex);
    if (!Number.isInteger(selectionIndex)) {
      return;
    }
    skillMentions.onChange(
      skillMentions.selected.filter((_, index) => index !== selectionIndex),
    );
    const tokenPartIndex = tokenParts.findIndex(
      (part) => part.selectionIndex === selectionIndex,
    );
    const nextParts = tokenParts.flatMap((part, index) => {
      if (part.selectionIndex === selectionIndex) {
        return [];
      }
      if (index === tokenPartIndex + 1 && part.kind === "text") {
        return [{ ...part, value: part.value.replace(/^\s/, "") }];
      }
      return [part];
    });
    onValueChange(nextParts.map((part) => part.value).join(""));
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
        aria-activedescendant={
          mentions.open && mentions.activeItemId
            ? `context-reference-option-${encodeURIComponent(
                mentions.activeItemId,
              )}`
            : undefined
        }
        aria-controls={mentions.open ? "context-reference-menu" : undefined}
        aria-expanded={mentions.open}
        aria-haspopup="listbox"
        aria-multiline="true"
        className={className}
        contentEditable={!disabled && !readOnly}
        data-placeholder={placeholder}
        role="textbox"
        suppressContentEditableWarning
        style={style}
        onCompositionStart={(event) => {
          isComposingRef.current = true;
          onCompositionStart?.(event);
        }}
        onCompositionEnd={(event) => {
          isComposingRef.current = false;
          onCompositionEnd?.(event);
          setCompositionVersion((version) => version + 1);
        }}
        onInput={(event) => {
          const editor = event.currentTarget;
          const nextValue = editor.textContent || "";
          const nextSelected = selectedReferencesVisibleInEditor(
            editor,
            skillMentions.selected,
          );
          if (nextSelected.length !== skillMentions.selected.length) {
            skillMentions.onChange(nextSelected);
          }
          mentions.handleInputValueChange(
            nextValue,
            getCaretOffset(editor) ?? nextValue.length,
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
        id="context-reference-menu"
        style={{
          bottom: "calc(100% + 12px)",
          left: 0,
          position: "absolute",
          right: 0,
          zIndex: 10,
        }}
      >
        <SkillMentionMenu
          activeIndex={mentions.activeIndex}
          error={skillMentions.error}
          items={mentions.filteredItems}
          loading={mentions.loading}
          onRetry={skillMentions.onRetry}
          open={mentions.open}
          query={mentions.query}
          onSelect={mentions.select}
        />
      </div>
    </div>
  );
});
