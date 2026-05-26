import { useMemo } from "react";
import {
  AgentScopeRuntimeMessageType,
  IAgentScopeRuntimeResponse,
} from "../types";
import AgentScopeRuntimeResponseBuilder from "./Builder";
import Message from "./Message";
import Tool from "./Tool";
import Reasoning from "./Reasoning";
import Error from "./Error";
import { Bubble, Markdown } from "@/components/agentscope-chat";
import Actions from "./Actions";
import Suggestions from "./Suggestions";
import RetryStatusMessage from "./RetryStatusMessage";
import { getCompletedReasoningFallbackText } from "./reasoningFallback";
// import { Avatar, Flex } from "antd";
// import { useChatAnywhereOptions } from "../../Context/ChatAnywhereOptionsContext";

type RetryMetadata = {
  retry_status?: unknown;
  metadata?: {
    retry_status?: unknown;
  };
};

function getRetryStatus(item: unknown) {
  const metadata = (item as { metadata?: RetryMetadata }).metadata;
  return metadata?.retry_status || metadata?.metadata?.retry_status;
}

export default function AgentScopeRuntimeResponseCard(props: {
  data: IAgentScopeRuntimeResponse;
  isLast?: boolean;
}) {
  // const avatar = useChatAnywhereOptions((v) => v.welcome.avatar);
  // const nick = useChatAnywhereOptions((v) => v.welcome.nick);
  const messages = useMemo(() => {
    return AgentScopeRuntimeResponseBuilder.mergeToolMessages(
      props.data.output,
    );
  }, [props.data.output]);
  const reasoningFallbackText = useMemo(() => {
    return getCompletedReasoningFallbackText(props.data, messages);
  }, [messages, props.data]);

  if (
    !messages?.length &&
    AgentScopeRuntimeResponseBuilder.maybeGenerating(props.data)
  )
    return <Bubble.Spin />;

  return (
    <>
      {/* {avatar && (
        <Flex align="center" gap={8} style={{ marginBottom: 8 }}>
          <Avatar src={avatar} />
          {nick && <span>{nick as string}</span>}
        </Flex>
      )} */}
      {messages.map((item) => {
        switch (item.type) {
          case AgentScopeRuntimeMessageType.MESSAGE: {
            // 检测重试状态消息，使用专用卡片渲染
            // SSE 流式路径: metadata.retry_status
            // 历史加载路径: metadata.metadata.retry_status（后端嵌套）
            const retryStatus = getRetryStatus(item);
            if (retryStatus) {
              return <RetryStatusMessage key={item.id} data={item} />;
            }
            return <Message key={item.id} data={item} />;
          }
          case AgentScopeRuntimeMessageType.PLUGIN_CALL:
          case AgentScopeRuntimeMessageType.PLUGIN_CALL_OUTPUT:
          case AgentScopeRuntimeMessageType.MCP_CALL:
          case AgentScopeRuntimeMessageType.MCP_CALL_OUTPUT:
            return <Tool key={item.id} data={item} />;
          case AgentScopeRuntimeMessageType.MCP_APPROVAL_REQUEST:
            return <Tool key={item.id} data={item} isApproval={true} />;
          case AgentScopeRuntimeMessageType.REASONING:
            return <Reasoning key={item.id} data={item} />;
          case AgentScopeRuntimeMessageType.ERROR:
            return <Error key={item.id} data={item} />;
          case AgentScopeRuntimeMessageType.HEARTBEAT:
            return null;
          default:
            console.warn(`[WIP] Unknown message type: ${item.type}`);
            return null;
        }
      })}
      {reasoningFallbackText && <Markdown content={reasoningFallbackText} />}
      {props.data.error && <Error data={props.data.error} />}
      <Actions {...props} />
      {props.data.suggestions?.length > 0 && (
        <Suggestions
          suggestions={props.data.suggestions}
          status={props.data.status}
        />
      )}
    </>
  );
}
