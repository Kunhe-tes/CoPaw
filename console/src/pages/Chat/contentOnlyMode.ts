export interface ChatContentOnlyRoute {
  chatId?: string;
  enabled: boolean;
  isChatRoute: boolean;
}

export function resolveChatContentOnlyRoute(
  pathname: string,
  showContentOnly: boolean,
): ChatContentOnlyRoute {
  const isChatRoute = pathname === "/chat" || pathname.startsWith("/chat/");
  const chatId = pathname.match(/^\/chat\/([^/]+)$/)?.[1];
  const enabled = Boolean(chatId) && showContentOnly;

  return {
    enabled,
    isChatRoute,
    ...(chatId ? { chatId } : {}),
  };
}
