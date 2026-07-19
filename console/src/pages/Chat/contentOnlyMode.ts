export const CHAT_CONTENT_ONLY_QUERY_PARAM = "showContentOnly";

export interface ChatContentOnlyRoute {
  chatId?: string;
  enabled: boolean;
  isChatRoute: boolean;
}

export function resolveChatContentOnlyRoute(
  pathname: string,
  search: string,
): ChatContentOnlyRoute {
  const isChatRoute = pathname === "/chat" || pathname.startsWith("/chat/");
  const chatId = pathname.match(/^\/chat\/([^/]+)$/)?.[1];
  const enabled =
    Boolean(chatId) &&
    new URLSearchParams(search).get(CHAT_CONTENT_ONLY_QUERY_PARAM) === "true";

  return {
    enabled,
    isChatRoute,
    ...(chatId ? { chatId } : {}),
  };
}
