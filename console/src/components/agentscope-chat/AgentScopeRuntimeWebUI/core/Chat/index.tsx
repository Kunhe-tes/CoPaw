import { useProviderContext } from "@/components/agentscope-chat";
import Input from "./Input";
import MessageList from "./MessageList";
import Style from "./styles";
import useChatController from "./hooks/useChatController";
import { useChatAnywhereSessionLoader } from "../Context/ChatAnywhereSessionsContext";
import { ChatAnywhereMessagesContext } from "../Context/ChatAnywhereMessagesContext";
import { useContextSelector } from "use-context-selector";
import { useChatContentOnly } from "@/components/agentscope-chat/ChatContentOnlyContext";

export default function Chat() {
  const isContentOnly = useChatContentOnly();
  const prefixCls = useProviderContext().getPrefixCls("chat-anywhere-chat");
  const { handleSubmit, handleCancel } = useChatController();
  useChatAnywhereSessionLoader({
    finishLoadingWithoutSession: isContentOnly,
  });
  // ==================== 首页改版 (Kun He) ====================
  // 当无消息时（欢迎态），隐藏底部输入框，因为欢迎页自带输入卡片
  const messages = useContextSelector(
    ChatAnywhereMessagesContext,
    (v) => v.messages,
  );
  const hasMessages = messages && messages.length > 0;
  // ==================== 首页改版结束 ====================

  return (
    <>
      <Style />
      <div className={prefixCls}>
        <MessageList onSubmit={handleSubmit} />
        {/* Input always rendered to handle pasteFile events, visually hidden when no messages */}
        {!isContentOnly && (
          <div style={{ display: hasMessages ? "block" : "none" }}>
            <Input onCancel={handleCancel} onSubmit={handleSubmit} />
          </div>
        )}
      </div>
    </>
  );
}
