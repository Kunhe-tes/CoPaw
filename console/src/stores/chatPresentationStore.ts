import { create } from "zustand";

export const CHAT_CONTENT_ONLY_QUERY_PARAM = "showContentOnly";

interface ChatPresentationState {
  showContentOnly: boolean;
  initializeFromUrl: (pathname: string, search: string) => void;
}

export function isChatContentOnlyRequested(
  pathname: string,
  search: string,
): boolean {
  const routePathname = pathname.replace(/^\/console(?=\/|$)/, "") || "/";

  return (
    /^\/chat\/[^/]+$/.test(routePathname) &&
    new URLSearchParams(search).get(CHAT_CONTENT_ONLY_QUERY_PARAM) === "true"
  );
}

export const useChatPresentationStore = create<ChatPresentationState>(
  (set) => ({
    showContentOnly: false,
    initializeFromUrl: (pathname, search) =>
      set({ showContentOnly: isChatContentOnlyRequested(pathname, search) }),
  }),
);

export function initializeChatPresentationFromUrl(
  pathname: string,
  search: string,
): void {
  useChatPresentationStore.getState().initializeFromUrl(pathname, search);
}
