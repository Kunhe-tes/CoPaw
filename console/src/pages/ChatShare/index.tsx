import { useEffect, useMemo, useState } from "react";
import { Alert, Empty, Spin } from "antd";
import {
  Bubble,
  AgentScopeRuntimeWebUIComposedProvider,
  type IAgentScopeRuntimeWebUIOptions,
} from "@/components/agentscope-chat";
import { useParams } from "react-router-dom";
import { chatApi } from "@/api/modules/chat";
import type { ChatShareSnapshot } from "@/api/types/chat";
import { convertMessages } from "../Chat/sessionApi";
import RuntimeRequestCard from "../Chat/components/RuntimeRequestCard";
import AgentScopeRuntimeResponseCard from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Response/Card";
import type {
  ChatRuntimeRequestCardData,
  ChatRuntimeResponseCardData,
} from "../Chat/messageMeta";
import { HtmlPreviewTrackingProvider } from "@/components/agentscope-chat/HtmlPreviewTrackingContext";
import { prepareShareMessages } from "./shareView";
import styles from "./index.module.less";

const READONLY_OPTIONS = {
  theme: { locale: "zh-CN", bubbleList: { pagination: false } },
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
  actions: { list: [], replace: false },
  api: { replaceMediaURL: (url: string) => url },
} as unknown as IAgentScopeRuntimeWebUIOptions;

function ReadOnlyStructuredCard(props: { code?: string; data?: unknown }) {
  const record = props.data && typeof props.data === "object"
    ? (props.data as { code?: unknown; data?: unknown })
    : null;
  const code = props.code || (typeof record?.code === "string" ? record.code : "会话记录");
  const data = record && "data" in record ? record.data : props.data;
  return (
    <section className={styles.structuredCard}>
      <strong>{code}</strong>
      <pre>{JSON.stringify(data ?? null, null, 2)}</pre>
    </section>
  );
}

function ReadOnlyResponseCard(props: {
  data: ChatRuntimeResponseCardData;
  isLast?: boolean;
}) {
  const data = useMemo(
    () => ({ ...props.data, suggestions: [] }),
    [props.data],
  );
  return <AgentScopeRuntimeResponseCard data={data} isLast={false} />;
}

const READONLY_CARDS = {
  AgentScopeRuntimeRequestCard: (props: { data: ChatRuntimeRequestCardData }) => (
    <RuntimeRequestCard {...props} />
  ),
  AgentScopeRuntimeResponseCard: ReadOnlyResponseCard,
  ApprovalAction: (props: { data: unknown }) => (
    <ReadOnlyStructuredCard code="审批记录" data={props.data} />
  ),
  PlanInteraction: (props: { data: unknown }) => (
    <ReadOnlyStructuredCard code="计划记录" data={props.data} />
  ),
  TaskRunGroupCard: (props: { data: unknown }) => (
    <ReadOnlyStructuredCard code="任务记录" data={props.data} />
  ),
  ResponseFeedback: (props: { data: unknown }) => (
    <ReadOnlyStructuredCard code="反馈记录" data={props.data} />
  ),
  WPlusSopEntryProposal: (props: { data: unknown }) => (
    <ReadOnlyStructuredCard code="SOP 记录" data={props.data} />
  ),
  ConversationCompactionBoundary: (props: { data: unknown }) => (
    <ReadOnlyStructuredCard code="会话归档边界" data={props.data} />
  ),
  ReadOnlyStructuredCard,
};

export default function ChatSharePage() {
  const { token = "" } = useParams<{ token: string }>();
  const [snapshot, setSnapshot] = useState<ChatShareSnapshot | null>(null);
  const [error, setError] = useState<"not-found" | "unavailable" | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      setError("not-found");
      setLoading(false);
      return;
    }
    void chatApi.getChatShare(token).then(setSnapshot).catch((reason) => {
      setError((reason as { status?: number })?.status === 404 ? "not-found" : "unavailable");
    }).finally(() => setLoading(false));
  }, [token]);

  if (loading) return <div className={styles.state}><Spin /></div>;
  if (error === "not-found") return <div className={styles.state}><Alert type="error" message="分享不存在" /></div>;
  if (error) return <div className={styles.state}><Alert type="error" message="分享服务暂不可用" /></div>;
  if (!snapshot) return <div className={styles.state}><Empty description="暂无分享内容" /></div>;

  const messages = prepareShareMessages(convertMessages(snapshot.messages || []));

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1>{snapshot.chat_name || "分享的会话"}</h1>
        <span>只读分享</span>
      </header>
      {messages.length === 0 ? (
        <Empty description="暂无分享内容" />
      ) : (
        <HtmlPreviewTrackingProvider value={{ disableEventRecording: true }}>
          <AgentScopeRuntimeWebUIComposedProvider options={READONLY_OPTIONS} cards={READONLY_CARDS}>
            <Bubble.List items={messages} order="asc" pagination={false} />
          </AgentScopeRuntimeWebUIComposedProvider>
        </HtmlPreviewTrackingProvider>
      )}
    </main>
  );
}
