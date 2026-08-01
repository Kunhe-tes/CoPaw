import {
  Bubble,
  useProviderContext,
  IAgentScopeRuntimeWebUIInputData,
} from "@/components/agentscope-chat";
import { ChatAnywhereMessagesContext } from "../../Context/ChatAnywhereMessagesContext";
import { useContextSelector } from "use-context-selector";
import { ChatAnywhereSessionsContext } from "../../Context/ChatAnywhereSessionsContext";
import cls from "classnames";
import Welcome from "../Welcome";
import { useChatAnywhereOptions } from "../../Context/ChatAnywhereOptionsContext";
import React from "react";
import { Result, Spin } from "antd";
import { useChatContentOnly } from "@/components/agentscope-chat/ChatContentOnlyContext";
import { chatApi } from "@/api/modules/chat";
import sessionApi, {
  convertArchivedPage,
} from "@/pages/Chat/sessionApi";
import type { IAgentScopeRuntimeWebUIMessage } from "@/components/agentscope-chat";
import useChatAnywhereEventEmitter from "../../Context/useChatAnywhereEventEmitter";

const CONVERSATION_COMPACTION_EVENT = "conversation_compacted";

export default function MessageList(props: {
  onSubmit: (data: IAgentScopeRuntimeWebUIInputData) => void;
}) {
  const isContentOnly = useChatContentOnly();
  const messages = useContextSelector(
    ChatAnywhereMessagesContext,
    (v) => v.messages,
  );
  const setMessages = useContextSelector(
    ChatAnywhereMessagesContext,
    (v) => v.setMessages,
  );
  const safeMessages = React.useMemo(
    () => [...(messages || [])].reverse(),
    [messages],
  );
  const prefixCls = useProviderContext().getPrefixCls(
    "chat-anywhere-message-list",
  );
  const currentSessionId = useContextSelector(
    ChatAnywhereSessionsContext,
    (v) => v.currentSessionId,
  );
  const isSessionLoading = useContextSelector(
    ChatAnywhereSessionsContext,
    (v) => v.isSessionLoading,
  );
  const sessionNotFound = useContextSelector(
    ChatAnywhereSessionsContext,
    (v) => v.sessionNotFound,
  );
  const bubbleListOptions = useChatAnywhereOptions((v) => v.theme?.bubbleList);
  const listRef = React.useRef<{
    scrollToBottom: () => void;
    getScrollElement: () => HTMLDivElement | null;
  } | null>(null);
  const prevMessagesLengthRef = React.useRef(safeMessages.length);
  const historyCursorRef = React.useRef<string | null>(null);
  const historyLoadingRef = React.useRef(false);
  const historyDoneRef = React.useRef(false);
  const historyGenerationRef = React.useRef(0);
  const isPrependingHistoryRef = React.useRef(false);
  const backendChatId = sessionApi.getChatIdForSession(currentSessionId || "");

  React.useEffect(() => {
    historyCursorRef.current = null;
    historyLoadingRef.current = false;
    historyDoneRef.current = false;
    historyGenerationRef.current += 1;
  }, [backendChatId]);

  const loadOlderHistory = React.useCallback(async () => {
    if (!backendChatId || historyLoadingRef.current || historyDoneRef.current) {
      return;
    }
    historyLoadingRef.current = true;
    const generation = historyGenerationRef.current;
    const scrollElement = listRef.current?.getScrollElement();
    const oldTop = scrollElement?.scrollTop ?? 0;
    try {
      const page = await chatApi.getChatHistory(
        backendChatId,
        historyCursorRef.current,
      );
      if (generation !== historyGenerationRef.current) return;
      historyCursorRef.current = page.next_cursor || null;
      historyDoneRef.current = !page.has_more;
      const older: IAgentScopeRuntimeWebUIMessage[] = convertArchivedPage(
        page.messages || [],
        page.boundaries || [],
      );
      isPrependingHistoryRef.current = older.length > 0;
      // @ts-ignore
      setMessages((current) => {
        const known = new Set(current.map((message) => message.id));
        return [...older.filter((message) => !known.has(message.id)), ...current];
      });
      requestAnimationFrame(() => {
        if (scrollElement && generation === historyGenerationRef.current) {
          scrollElement.scrollTop = oldTop;
        }
      });
    } finally {
      if (generation === historyGenerationRef.current) {
        historyLoadingRef.current = false;
      }
    }
  }, [backendChatId, setMessages]);

  useChatAnywhereEventEmitter(
    {
      type: CONVERSATION_COMPACTION_EVENT,
      callback: (event) => {
        const detail = event.detail as { chat_id?: unknown } | undefined;
        if (
          typeof detail?.chat_id !== "string" ||
          detail.chat_id !== backendChatId ||
          !currentSessionId
        ) {
          return;
        }
        historyCursorRef.current = null;
        historyDoneRef.current = false;
        historyGenerationRef.current += 1;
        void sessionApi
          .getSession(currentSessionId)
          .then((session) => {
            if (
              sessionApi.getChatIdForSession(currentSessionId) ===
              detail.chat_id
            ) {
              setMessages(session.messages || []);
            }
          })
          .catch(() => undefined);
      },
    },
    [backendChatId, currentSessionId, setMessages],
  );

  React.useEffect(() => {
    if (
      safeMessages.length > prevMessagesLengthRef.current &&
      !isPrependingHistoryRef.current
    ) {
      listRef.current?.scrollToBottom();
    }
    isPrependingHistoryRef.current = false;
    prevMessagesLengthRef.current = safeMessages.length;
  }, [safeMessages.length]);

  // 当正在加载会话时，显示加载指示器而不是欢迎页
  // 避免在切换会话时闪现"新建会话"页面
  if (isSessionLoading) {
    return (
      <div className={cls(prefixCls, `${prefixCls}-loading`)}>
        <Spin size="large" />
      </div>
    );
  }

  if (isContentOnly && sessionNotFound) {
    return (
      <div className={cls(prefixCls, `${prefixCls}-welcome`)}>
        <Result
          status="404"
          title="会话不存在"
          subTitle="该会话不存在或已被删除"
        />
      </div>
    );
  }

  if (safeMessages.length === 0) {
    return (
      <div className={cls(prefixCls, `${prefixCls}-welcome`)}>
        {!isContentOnly && <Welcome onSubmit={props.onSubmit} />}
      </div>
    );
  }

  return (
    <Bubble.List
      ref={listRef}
      pagination={bubbleListOptions?.pagination ?? true}
      order="desc"
      key={currentSessionId}
      classNames={{
        wrapper: prefixCls,
      }}
      items={safeMessages}
      onReachStart={() => void loadOlderHistory()}
    />
  );
}
