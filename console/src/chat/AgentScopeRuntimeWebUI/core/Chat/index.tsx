import React from 'react';
import { useProviderContext } from "@/chat";
import Input from "./Input";
import MessageList from "./MessageList";
import Style from './styles';
import useChatController from "./hooks/useChatController";
import useChatAnywhereEventEmitter from "../Context/useChatAnywhereEventEmitter";

export default function Chat() {
  const prefixCls = useProviderContext().getPrefixCls('chat-anywhere-chat');
  const { handleSubmit, handleCancel } = useChatController();
  const inputRef = React.useRef<{
    setContent: (content: string) => void;
  } | null>(null);

  // 监听编辑事件
  useChatAnywhereEventEmitter({
    type: 'handleEdit',
    callback: async (data) => {
      if (inputRef.current) {
        inputRef.current.setContent(data.detail.content);
      }
    }
  });

  return <>
    <Style />
    <div className={prefixCls}>
      <MessageList onSubmit={handleSubmit} />
      <Input ref={inputRef} onCancel={handleCancel} onSubmit={handleSubmit} />
    </div>
  </>;
}