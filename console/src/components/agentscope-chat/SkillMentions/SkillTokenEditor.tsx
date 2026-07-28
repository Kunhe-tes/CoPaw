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
    dataIcon: "api",
    label: "MCP 工具",
    path: "M917.7 148.8l-42.4-42.4c-1.6-1.6-3.6-2.3-5.7-2.3s-4.1.8-5.7 2.3l-76.1 76.1a199.27 199.27 0 00-112.1-34.3c-51.2 0-102.4 19.5-141.5 58.6L432.3 308.7a8.03 8.03 0 000 11.3L704 591.7c1.6 1.6 3.6 2.3 5.7 2.3 2 0 4.1-.8 5.7-2.3l101.9-101.9c68.9-69 77-175.7 24.3-253.5l76.1-76.1c3.1-3.2 3.1-8.3 0-11.4zM769.1 441.7l-59.4 59.4-186.8-186.8 59.4-59.4c24.9-24.9 58.1-38.7 93.4-38.7 35.3 0 68.4 13.7 93.4 38.7 24.9 24.9 38.7 58.1 38.7 93.4 0 35.3-13.8 68.4-38.7 93.4zm-190.2 105a8.03 8.03 0 00-11.3 0L501 613.3 410.7 523l66.7-66.7c3.1-3.1 3.1-8.2 0-11.3L441 408.6a8.03 8.03 0 00-11.3 0L363 475.3l-43-43a7.85 7.85 0 00-5.7-2.3c-2 0-4.1.8-5.7 2.3L206.8 534.2c-68.9 69-77 175.7-24.3 253.5l-76.1 76.1a8.03 8.03 0 000 11.3l42.4 42.4c1.6 1.6 3.6 2.3 5.7 2.3s4.1-.8 5.7-2.3l76.1-76.1c33.7 22.9 72.9 34.3 112.1 34.3 51.2 0 102.4-19.5 141.5-58.6l101.9-101.9c3.1-3.1 3.1-8.2 0-11.3l-43-43 66.7-66.7c3.1-3.1 3.1-8.2 0-11.3l-36.6-36.2zM441.7 769.1a131.32 131.32 0 01-93.4 38.7c-35.3 0-68.4-13.7-93.4-38.7a131.32 131.32 0 01-38.7-93.4c0-35.3 13.7-68.4 38.7-93.4l59.4-59.4 186.8 186.8-59.4 59.4z",
  },
  skill: {
    dataIcon: "thunderbolt",
    label: "技能",
    path: "M848 359.3H627.7L825.8 109c4.1-5.3.4-13-6.3-13H436c-2.8 0-5.5 1.5-6.9 4L170 547.5c-3.1 5.3.7 12 6.9 12h174.4l-89.4 357.6c-1.9 7.8 7.5 13.3 13.3 7.7L853.5 373c5.2-4.9 1.7-13.7-5.5-13.7zM378.2 732.5l60.3-241H281.1l189.6-327.4h224.6L487 427.4h211L378.2 732.5z",
  },
  workspace_file: {
    dataIcon: "file",
    label: "文件",
    path: "M854.6 288.6L639.4 73.4c-6-6-14.1-9.4-22.6-9.4H192c-17.7 0-32 14.3-32 32v832c0 17.7 14.3 32 32 32h640c17.7 0 32-14.3 32-32V311.3c0-8.5-3.4-16.7-9.4-22.7zM790.2 326H602V137.8L790.2 326zm1.8 562H232V136h302v216a42 42 0 0042 42h216v494z",
  },
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
    svg.setAttribute("data-icon", iconDetails.dataIcon);
    svg.setAttribute("fill", "currentColor");
    svg.setAttribute("height", "11");
    svg.setAttribute("viewBox", "64 64 896 896");
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
