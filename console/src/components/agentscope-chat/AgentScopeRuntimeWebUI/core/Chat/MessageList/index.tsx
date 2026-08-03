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
import sessionApi, { convertArchivedPage } from "@/pages/Chat/sessionApi";
import useChatAnywhereEventEmitter from "../../Context/useChatAnywhereEventEmitter";
import useHistoryPreload from "@/components/agentscope-chat/Bubble/hooks/useHistoryPreload";
import { getScrollTopAfterAnchorOffset } from "@/components/agentscope-chat/Bubble/hooks/scrollAnchor";

const CONVERSATION_COMPACTION_EVENT = "conversation_compacted";

function getVisibleMessageAnchor(scrollElement: HTMLElement) {
  const containerRect = scrollElement.getBoundingClientRect();
  const anchorElement = Array.from(
    scrollElement.querySelectorAll<HTMLElement>("[data-role][id]"),
  )
    .map((element) => ({ element, rect: element.getBoundingClientRect() }))
    .filter(
      ({ rect }) =>
        rect.bottom > containerRect.top && rect.top < containerRect.bottom,
    )
    .sort((left, right) => left.rect.top - right.rect.top)[0];

  if (!anchorElement) return null;
  return {
    messageId: anchorElement.element.id,
    offset: anchorElement.rect.top - containerRect.top,
  };
}

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
  const [historyScrollElement, setHistoryScrollElement] =
    React.useState<HTMLDivElement | null>(null);
  const prevMessagesLengthRef = React.useRef(safeMessages.length);
  const historyCursorRef = React.useRef<string | null>(null);
  const historyLoadingRef = React.useRef(false);
  const historyDoneRef = React.useRef(false);
  const loadedArchiveMessageIdsRef = React.useRef(new Set<string>());
  const loadedBoundaryIdsRef = React.useRef(new Set<string>());
  const historyGenerationRef = React.useRef(0);
  const compactionRefreshRef = React.useRef(0);
  const activeSessionRef = React.useRef(currentSessionId);
  const isPrependingHistoryRef = React.useRef(false);
  const isAtLatestRef = React.useRef(true);
  const pendingHistoryAnchorRef = React.useRef<{
    messageId: string;
    offset: number;
    oldScrollTop: number;
  } | null>(null);
  const [historyExhausted, setHistoryExhausted] = React.useState(false);
  const [historyLoadState, setHistoryLoadState] = React.useState<
    "idle" | "loading" | "error" | "exhausted"
  >("idle");
  const backendChatId = sessionApi.getChatIdForSession(currentSessionId || "");

  React.useLayoutEffect(() => {
    activeSessionRef.current = currentSessionId;
    compactionRefreshRef.current += 1;
  }, [currentSessionId]);

  React.useEffect(() => {
    historyCursorRef.current = null;
    historyLoadingRef.current = false;
    historyDoneRef.current = false;
    loadedArchiveMessageIdsRef.current = new Set();
    loadedBoundaryIdsRef.current = new Set();
    historyGenerationRef.current += 1;
    setHistoryExhausted(false);
    setHistoryLoadState("idle");
  }, [backendChatId]);

  const loadOlderHistory = React.useCallback(async () => {
    if (!backendChatId || historyLoadingRef.current || historyDoneRef.current) {
      return;
    }
    historyLoadingRef.current = true;
    setHistoryLoadState("loading");
    const generation = historyGenerationRef.current;
    try {
      const page = await chatApi.getChatHistory(
        backendChatId,
        historyCursorRef.current,
      );
      if (generation !== historyGenerationRef.current) return;
      historyDoneRef.current = !page.has_more;
      setHistoryExhausted(!page.has_more);
      historyCursorRef.current = page.next_cursor || null;
      const unseenMessages = (page.messages || []).filter((message) => {
        if (typeof message.id !== "string") return true;
        if (loadedArchiveMessageIdsRef.current.has(message.id)) return false;
        loadedArchiveMessageIdsRef.current.add(message.id);
        return true;
      });
      const unseenBoundaries = (page.boundaries || []).filter((boundary) => {
        if (loadedBoundaryIdsRef.current.has(boundary.id)) return false;
        loadedBoundaryIdsRef.current.add(boundary.id);
        return true;
      });
      const older = convertArchivedPage(
        unseenMessages,
        unseenBoundaries,
      ).map((message) => ({ ...message, history: true }));
      const knownMessageIds = new Set(
        (messages || []).map((message) => message.id),
      );
      const uniqueOlder = older.filter(
        (message) => !knownMessageIds.has(message.id),
      );
      const scrollElement = listRef.current?.getScrollElement();
      if (uniqueOlder.length > 0 && scrollElement) {
        const anchor = getVisibleMessageAnchor(scrollElement);
        pendingHistoryAnchorRef.current = anchor
          ? { ...anchor, oldScrollTop: scrollElement.scrollTop }
          : null;
      }
      isPrependingHistoryRef.current = uniqueOlder.length > 0;
      // @ts-expect-error Context exposes a React-style updater at runtime but omits it from its public type.
      setMessages((current) => {
        const known = new Set(current.map((message) => message.id));
        return [
          ...uniqueOlder.filter((message) => !known.has(message.id)),
          ...current,
        ];
      });
      setHistoryLoadState(
        !page.has_more && uniqueOlder.length === 0 ? "exhausted" : "idle",
      );
    } catch {
      if (generation === historyGenerationRef.current) {
        setHistoryLoadState("error");
      }
    } finally {
      if (generation === historyGenerationRef.current) {
        historyLoadingRef.current = false;
      }
    }
  }, [backendChatId, messages, setMessages]);

  React.useLayoutEffect(() => {
    const nextScrollElement = listRef.current?.getScrollElement() ?? null;
    setHistoryScrollElement((current) =>
      current === nextScrollElement ? current : nextScrollElement,
    );
  }, [currentSessionId, safeMessages.length]);

  React.useLayoutEffect(() => {
    const anchor = pendingHistoryAnchorRef.current;
    const scrollElement = listRef.current?.getScrollElement();
    if (!anchor || !scrollElement) return;

    const anchorElement = document.getElementById(anchor.messageId);
    if (anchorElement && scrollElement.contains(anchorElement)) {
      const nextOffset =
        anchorElement.getBoundingClientRect().top -
        scrollElement.getBoundingClientRect().top;
      scrollElement.scrollTop = getScrollTopAfterAnchorOffset({
        oldScrollTop: anchor.oldScrollTop,
        previousOffset: anchor.offset,
        nextOffset,
      });
    }
    pendingHistoryAnchorRef.current = null;
  }, [safeMessages]);

  useHistoryPreload({
    scrollElement: historyScrollElement,
    onNearStart: loadOlderHistory,
    disabled:
      !backendChatId || historyExhausted || historyLoadState !== "idle",
    resetKey: backendChatId,
  });

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
        setHistoryExhausted(false);
        setHistoryLoadState("idle");
        const refresh = ++compactionRefreshRef.current;
        const requestedSessionId = currentSessionId;
        const requestedChatId = detail.chat_id;
        void sessionApi
          .getSession(requestedSessionId)
          .then((session) => {
            if (
              refresh === compactionRefreshRef.current &&
              activeSessionRef.current === requestedSessionId &&
              sessionApi.getChatIdForSession(requestedSessionId) ===
                requestedChatId
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
      !isPrependingHistoryRef.current &&
      isAtLatestRef.current
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

  const historyStatus =
    historyLoadState === "loading"
      ? "正在加载更早的消息…"
      : historyLoadState === "exhausted"
        ? "已到达会话开始处"
        : historyLoadState === "error"
          ? "加载历史消息失败"
          : null;

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
      preserveScrollPosition={isPrependingHistoryRef.current}
      autoScrollToBottom="initial"
      onBottomStateChange={(isAtBottom) => {
        isAtLatestRef.current = isAtBottom;
      }}
      topContent={
        <div
          aria-live="polite"
          role={historyLoadState === "error" ? "alert" : "status"}
          style={{
            alignItems: "center",
            color: historyLoadState === "error" ? "#B94A4F" : "#8A94A6",
            display: "flex",
            flexShrink: 0,
            fontSize: 13,
            height: 32,
            justifyContent: "center",
            pointerEvents: historyLoadState === "error" ? "auto" : "none",
          }}
        >
          {historyStatus}
          {historyLoadState === "error" ? (
            <button
              onClick={() => void loadOlderHistory()}
              style={{ marginLeft: 8 }}
              type="button"
            >
              重试
            </button>
          ) : null}
        </div>
      }
    />
  );
}
