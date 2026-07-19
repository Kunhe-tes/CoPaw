import {
  resolveChatContentOnlyRoute,
  type ChatContentOnlyRoute,
} from "@/pages/Chat/contentOnlyMode";

export interface MainLayoutPresentation {
  contentOnlyRoute: ChatContentOnlyRoute;
  hideGlobalShell: boolean;
}

export function resolveMainLayoutPresentation(input: {
  hideMenu: boolean;
  pathname: string;
  search: string;
}): MainLayoutPresentation {
  const contentOnlyRoute = resolveChatContentOnlyRoute(
    input.pathname,
    input.search,
  );

  return {
    contentOnlyRoute,
    hideGlobalShell: input.hideMenu || contentOnlyRoute.enabled,
  };
}
