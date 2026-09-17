export const CHAT_INPUT_APPEND_TEXT_EVENT =
  "agentscope-runtime:append-input-text";
export const CHAT_INPUT_REPLACE_TEXT_EVENT =
  "agentscope-runtime:replace-input-text";

export interface ChatInputAppendTextPayload {
  content: string;
}

export interface ChatInputReplaceTextPayload {
  content: string;
}

export function appendChatInputText(current: string, content: string): string {
  if (!content) {
    return current;
  }
  return current ? `${current}\n${content}` : content;
}

export function emitChatInputAppendText(content: string): void {
  if (!content) {
    return;
  }

  document.dispatchEvent(
    new CustomEvent<ChatInputAppendTextPayload>(CHAT_INPUT_APPEND_TEXT_EVENT, {
      detail: { content },
    }),
  );
}

export function emitChatInputReplaceText(content: string): void {
  if (!content) {
    return;
  }

  document.dispatchEvent(
    new CustomEvent<ChatInputReplaceTextPayload>(
      CHAT_INPUT_REPLACE_TEXT_EVENT,
      { detail: { content } },
    ),
  );
}
