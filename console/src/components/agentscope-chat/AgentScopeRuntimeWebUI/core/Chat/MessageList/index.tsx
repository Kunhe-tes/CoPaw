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
import useTopOverscroll, {
  TOP_PULL_THRESHOLD,
} from "@/components/agentscope-chat/Bubble/hooks/useTopOverscroll";
import { getScrollTopAfterPrepend } from "@/components/agentscope-chat/Bubble/hooks/scrollAnchor";

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
  const [historyScrollElement, setHistoryScrollElement] =
    React.useState<HTMLDivElement | null>(null);
  const prevMessagesLengthRef = React.useRef(safeMessages.length);
  const historyCursorRef = React.useRef<string | null>(null);
  const historyLoadingRef = React.useRef(false);
  const historyDoneRef = React.useRef(false);
  const historyGenerationRef = React.useRef(0);
  const compactionRefreshRef = React.useRef(0);
  const activeSessionRef = React.useRef(currentSessionId);
  const isPrependingHistoryRef = React.useRef(false);
  const pendingHistoryAnchorRef = React.useRef<{
    clientHeight: number;
    oldScrollHeight: number;
    oldScrollTop: number;
  } | null>(null);
  const [historyExhausted, setHistoryExhausted] = React.useState(false);
  const backendChatId = sessionApi.getChatIdForSession(currentSessionId || "");

  React.useLayoutEffect(() => {
    activeSessionRef.current = currentSessionId;
    compactionRefreshRef.current += 1;
  }, [currentSessionId]);

  React.useEffect(() => {
    historyCursorRef.current = null;
    historyLoadingRef.current = false;
    historyDoneRef.current = false;
    historyGenerationRef.current += 1;
    setHistoryExhausted(false);
  }, [backendChatId]);

  const loadOlderHistory = React.useCallback(async () => {
    if (!backendChatId || historyLoadingRef.current || historyDoneRef.current) {
      return;
    }
    historyLoadingRef.current = true;
    const generation = historyGenerationRef.current;
    try {
      const page = await chatApi.getChatHistory(
        backendChatId,
        historyCursorRef.current,
      );
      if (generation !== historyGenerationRef.current) return;
      historyCursorRef.current = page.next_cursor || null;
      historyDoneRef.current = !page.has_more;
      setHistoryExhausted(!page.has_more);
      const older: IAgentScopeRuntimeWebUIMessage[] = convertArchivedPage(
        page.messages || [],
        page.boundaries || [],
      );
      const knownMessageIds = new Set(
        (messages || []).map((message) => message.id),
      );
      const uniqueOlder = older.filter(
        (message) => !knownMessageIds.has(message.id),
      );
      const scrollElement = listRef.current?.getScrollElement();
      if (uniqueOlder.length > 0 && scrollElement) {
        pendingHistoryAnchorRef.current = {
          clientHeight: scrollElement.clientHeight,
          oldScrollHeight: scrollElement.scrollHeight,
          oldScrollTop: scrollElement.scrollTop,
        };
      }
      isPrependingHistoryRef.current = uniqueOlder.length > 0;
      // @ts-expect-error Context exposes a React-style updater at runtime but omits it from its public type.
      setMessages((current) => {
        const known = new Set(current.map((message) => message.id));
        return [...older.filter((message) => !known.has(message.id)), ...current];
      });
    } catch {
      // The next upward scroll remains a retry; no persistent UI is needed.
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

    scrollElement.scrollTop = getScrollTopAfterPrepend({
      clientHeight: anchor.clientHeight,
      newScrollHeight: scrollElement.scrollHeight,
      oldScrollHeight: anchor.oldScrollHeight,
      oldScrollTop: anchor.oldScrollTop,
      order: "desc",
    });
    pendingHistoryAnchorRef.current = null;
  }, [safeMessages]);

  const loadOlderHistoryFromPull = React.useCallback(
    async () => loadOlderHistory(),
    [loadOlderHistory],
  );
  const historyPull = useTopOverscroll({
    scrollElement: historyScrollElement,
    onTriggered: loadOlderHistoryFromPull,
    disabled: !backendChatId || historyExhausted,
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

  const historyPullLabel = {
    pulling: "加载更早历史",
    ready: "松开加载更早历史",
    loading: "正在加载更早历史",
  }[historyPull.state];

  return (
    <div style={{ height: "100%", position: "relative" }}>
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
      />
      {historyPullLabel && (
        <div
          aria-live="polite"
          role="status"
          style={{
            alignItems: "center",
            color: "#8A94A6",
            display: "flex",
            flexDirection: "column",
            fontSize: 13,
            gap: 4,
            left: 0,
            pointerEvents: "none",
            position: "absolute",
            right: 0,
            top: 8,
            transform: `translateY(${historyPull.visualOffset}px)`,
            transition:
              historyPull.state === "loading"
                ? "none"
                : "transform 80ms ease-out",
          }}
        >
          <span>{historyPullLabel}</span>
          <progress
            aria-label="加载更早历史进度"
            max={TOP_PULL_THRESHOLD}
            value={
              historyPull.state === "loading"
                ? TOP_PULL_THRESHOLD
                : historyPull.visualOffset
            }
          />
        </div>
      )}
    </div>
  );
}
