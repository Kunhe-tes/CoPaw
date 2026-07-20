import { createContext, useContext, type ReactNode } from "react";

const ChatContentOnlyContext = createContext(false);

export function ChatContentOnlyProvider(props: {
  children: ReactNode;
  enabled: boolean;
}) {
  return (
    <ChatContentOnlyContext.Provider value={props.enabled}>
      {props.children}
    </ChatContentOnlyContext.Provider>
  );
}

export function useChatContentOnly(): boolean {
  return useContext(ChatContentOnlyContext);
}
