import { fetchSuggestions } from "@/api/modules/suggestions";
import {
  extractCopyableText,
  extractUserMessageText,
} from "@/pages/Chat/utils";
import { useIframeStore } from "@/stores/iframeStore";
import { isSuggestionsDisabledForSource } from "@/utils/sourceFeatures";
import { useCallback, useEffect, useRef } from "react";
import { useContextSelector } from "use-context-selector";
import { ChatAnywhereSessionsContext } from "../../Context/ChatAnywhereSessionsContext";
import { useChatAnywhereOptions } from "../../Context/ChatAnywhereOptionsContext";

/**
 * 猜你想问建议获取 Hook
 *
 * 在响应完成后请求前端 external/mock suggestions API，并更新到当前响应中。
 */
export default function useSuggestionsPolling(options: {
  currentQARef: React.MutableRefObject<{
    request?: any;
    response?: any;
    abortController?: AbortController;
  }>;
  updateMessage: (message: any) => void;
}) {
  const { currentQARef, updateMessage } = options;

  const currentSessionId = useContextSelector(
    ChatAnywhereSessionsContext,
    (v) => v.currentSessionId,
  );

  const sessionApi = useChatAnywhereOptions((v) => v.session?.api);
  const source = useIframeStore((state) => state.source);
  const sessionIdRef = useRef(currentSessionId);
  const activePollResponseIdRef = useRef<string | null>(null);

  useEffect(() => {
    sessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  const pollSuggestions = useCallback(async () => {
    if (isSuggestionsDisabledForSource(source)) {
      console.debug("[Suggestions] Disabled for source:", source);
      return;
    }

    const sessionId = sessionIdRef.current;
    if (!sessionId) {
      console.debug("[Suggestions] No session ID available");
      return;
    }

    const currentRequest = currentQARef.current.request;
    const currentResponse = currentQARef.current.response;
    const turnId = currentResponse?.id;
    if (!turnId) {
      console.debug("[Suggestions] No response ID available");
      return;
    }

    activePollResponseIdRef.current = turnId;

    try {
      await (sessionApi as any)?.getSessionList?.();
    } catch (error) {
      console.debug("[Suggestions] getSessionList failed:", error);
    }

    const chatId =
      (sessionApi as any)?.getRealIdForSession?.(sessionId) ?? sessionId;
    const userMessage = extractUserMessageText(
      currentRequest?.cards?.[0]?.data?.input?.[0] ?? {},
    ).trim();
    const assistantMessage = extractCopyableText(
      currentResponse?.cards?.[0]?.data ?? {},
    ).trim();

    if (!userMessage || !assistantMessage) {
      console.debug("[Suggestions] Missing request or response text");
      return;
    }

    console.debug(
      "[Suggestions] Fetching suggestions for chatId:",
      chatId,
      "turnId:",
      turnId,
    );

    try {
      const suggestions = await fetchSuggestions({
        chatId,
        turnId,
        userMessage,
        assistantMessage,
      });

      if (activePollResponseIdRef.current !== turnId) {
        console.debug(
          "[Suggestions] Request cancelled, responseId mismatch. Expected:",
          turnId,
          "Active:",
          activePollResponseIdRef.current,
        );
        return;
      }

      if (!suggestions.length) {
        return;
      }

      const latestResponse = currentQARef.current.response;
      if (latestResponse?.id !== turnId) {
        console.debug(
          "[Suggestions] Response ID mismatch, skipping update. Expected:",
          turnId,
          "Current:",
          latestResponse?.id,
        );
        return;
      }

      if (latestResponse?.cards?.[0]?.data) {
        const updatedCards = [
          {
            ...latestResponse.cards[0],
            data: {
              ...latestResponse.cards[0].data,
              suggestions,
            },
          },
          ...latestResponse.cards.slice(1),
        ];

        currentQARef.current.response = {
          ...latestResponse,
          cards: updatedCards,
        };

        updateMessage(currentQARef.current.response);
      }
    } catch (error) {
      console.debug("[Suggestions] Fetch failed:", error);
    }
  }, [currentQARef, updateMessage, sessionApi, source]);

  return { pollSuggestions };
}
