import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import type {
  ChatGoalProposalCardData,
  ChatPlanReviewCardData,
} from "./messageMeta";

export interface ChatPlanReviewRenderContextValue {
  onContinueModifying?: (data: ChatPlanReviewCardData) => void;
  onPlanModeDecision?: (enabled: boolean) => void;
  onConfirmGoalProposal?: (
    data: ChatGoalProposalCardData,
  ) => Promise<{ goal_id: string }>;
}

const ChatPlanReviewRenderContext =
  createContext<ChatPlanReviewRenderContextValue>({});

export function ChatPlanReviewRenderProvider(props: {
  children: ReactNode;
  value: ChatPlanReviewRenderContextValue;
}) {
  return (
    <ChatPlanReviewRenderContext.Provider value={props.value}>
      {props.children}
    </ChatPlanReviewRenderContext.Provider>
  );
}

export function useChatPlanReviewRenderContext() {
  return useContext(ChatPlanReviewRenderContext);
}
