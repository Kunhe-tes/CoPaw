import { useEffect, useRef, useState } from "react";
import { Empty, Spin } from "antd";
import {
  AgentScopeRuntimeWebUIComposedProvider,
  Bubble,
  IAgentScopeRuntimeWebUIMessage,
  IAgentScopeRuntimeWebUIOptions,
} from "@/components/agentscope-chat";
import { tracingApi } from "../../../../../api/modules/tracing";
import type { Message } from "../../../../../api/types";
import {
  convertMessages,
} from "../../../../Chat/sessionApi";
import RuntimeRequestCard from "../../../../Chat/components/RuntimeRequestCard";
import RuntimeResponseCard from "../../../../Chat/components/RuntimeResponseCard";
import type {
  ChatRuntimeRequestCardData,
  ChatRuntimeResponseCardData,
} from "../../../../Chat/messageMeta";
import ConversationQuickNav from "../../../../../components/ConversationQuickNav";
import styles from "./index.module.less";

const READONLY_OPTIONS: IAgentScopeRuntimeWebUIOptions = {
  theme: {
    locale: "zh-CN",
    bubbleList: {
      pagination: false,
    },
  },
  session: {
    multiple: false,
    api: {
      getSessionList: async () => [],
      getSession: async () => ({ id: "", name: "", messages: [] }),
      createSession: async () => [],
      updateSession: async () => [],
      removeSession: async () => [],
    },
  },
  actions: {
    list: [],
    replace: false,
  },
  api: {
    replaceMediaURL: (url: string) => url,
  },
} as unknown as IAgentScopeRuntimeWebUIOptions;

const READONLY_CARDS = {
  AgentScopeRuntimeRequestCard: (props: {
    data: ChatRuntimeRequestCardData;
  }) => <RuntimeRequestCard {...props} />,
  AgentScopeRuntimeResponseCard: (props: {
    data: ChatRuntimeResponseCardData;
    isLast?: boolean;
  }) => <RuntimeResponseCard {...props} />,
};

interface ReadOnlySessionChatProps {
  selectedSessionId: string | null;
  chatIdBySessionId: Record<string, string>;
  targetUserId?: string;
  mockMessages?: Message[];
}

export default function ReadOnlySessionChat({
  selectedSessionId,
  chatIdBySessionId,
  targetUserId,
  mockMessages,
}: ReadOnlySessionChatProps) {
  const requestSeqRef = useRef(0);
  const chatContentRef = useRef<HTMLDivElement | null>(null);
  const [chatMessages, setChatMessages] = useState<
    IAgentScopeRuntimeWebUIMessage[]
  >([]);
  const [chatLoading, setChatLoading] = useState(false);

  useEffect(() => {
    const seq = requestSeqRef.current + 1;
    requestSeqRef.current = seq;
    setChatMessages([]);

    if (!selectedSessionId) {
      setChatLoading(false);
      return;
    }

    if (mockMessages) {
      setChatMessages(convertMessages(mockMessages));
      setChatLoading(false);
      return;
    }

    setChatLoading(true);
    const loadChatHistory = async () => {
      try {
        const chatId = chatIdBySessionId[selectedSessionId];
        if (!chatId) {
          return;
        }

        if (!targetUserId) {
          return;
        }

        const history = await tracingApi.getUserChat(targetUserId, chatId);
        if (requestSeqRef.current !== seq) return;

        const messages = convertMessages(history.messages || []);
        setChatMessages(messages);
      } catch (error) {
        console.error("Failed to load chat history:", error);
      } finally {
        if (requestSeqRef.current === seq) {
          setChatLoading(false);
        }
      }
    };

    void loadChatHistory();
  }, [selectedSessionId, chatIdBySessionId, targetUserId, mockMessages]);

  if (!selectedSessionId) {
    return (
      <div className={styles.readonlyChat}>
        {/* <div className={styles.readonlyChatTitle}>聊天记录</div> */}
        <div className={styles.readonlyChatEmpty}>
          <Empty description="请选择左侧会话卡片查看聊天内容" />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.readonlyChat}>
      <div className={styles.readonlyChatTitleRow}>
        <div className={styles.readonlyChatTitle}>聊天记录</div>
        {/* {titleTag}
        <Tag color="green">只读</Tag> */}
      </div>

      {chatLoading ? (
        <div className={styles.readonlyChatLoading}>
          <Spin />
        </div>
      ) : chatMessages.length === 0 ? (
        <div className={styles.readonlyChatEmpty}>
          <Empty description="暂无聊天内容" />
        </div>
      ) : (
        <AgentScopeRuntimeWebUIComposedProvider
          options={READONLY_OPTIONS}
          cards={READONLY_CARDS}
        >
          <div ref={chatContentRef} className={styles.readonlyChatBubbleList}>
            <Bubble.List
              pagination={false}
              order="asc"
              items={chatMessages}
              classNames={{
                wrapper: styles.readonlyBubbleWrapper,
                list: styles.readonlyBubbleList,
              }}
            />
            <ConversationQuickNav
              messages={chatMessages}
              scrollRootRef={chatContentRef}
            />
          </div>
        </AgentScopeRuntimeWebUIComposedProvider>
      )}
    </div>
  );
}
