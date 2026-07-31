import type { WPlusSopState } from "@/api/types/wplusSop";

export const WPLUS_SOP_REPLAY_EVENT = "wplus-sop:replay-in-chat";

export interface WPlusSopReplayDetail {
  query: string;
  proposal_id: string;
  suppression_token: string;
}

export interface WPlusSopEntryProposalProjection {
  proposal_id: string;
  mode: "explicit" | "implicit";
  status: "pending" | "confirmed" | "rejected";
  session_id?: string;
}

export interface WPlusSopSessionProjection {
  session_id: string;
  title: string;
  state: WPlusSopState;
  state_version: number;
  last_event_kind?: string;
}

export interface WPlusSopChatProjection {
  entryProposal: WPlusSopEntryProposalProjection | null;
  session: WPlusSopSessionProjection | null;
}

const WPLUS_SOP_STATES = new Set<WPlusSopState>([
  "GeneratingStageProposal",
  "AwaitingQueueConfirmation",
  "GeneratingQuestions",
  "AwaitingAnswer",
  "GeneratingTrial",
  "ExecutingTrial",
  "AwaitingTrialFeedback",
  "AwaitingStageConfirmation",
  "FinalizingOutputs",
  "MemoryReview",
  "PendingExit",
  "Paused",
  "RecoverableFailure",
  "Completed",
  "Terminated",
]);

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

export function readWPlusSopChatProjection(
  metadata: unknown,
): WPlusSopChatProjection {
  const root = asRecord(metadata);
  const entry = asRecord(root?.wplus_sop_entry_proposal);
  const projectedSession = asRecord(root?.wplus_sop_session);

  const proposalId =
    typeof entry?.proposal_id === "string" ? entry.proposal_id : "";
  const proposalMode = entry?.mode;
  const proposalStatus = entry?.status;
  const entryProposal: WPlusSopEntryProposalProjection | null =
    proposalId &&
    (proposalMode === "explicit" || proposalMode === "implicit") &&
    (proposalStatus === "pending" ||
      proposalStatus === "confirmed" ||
      proposalStatus === "rejected")
      ? {
          proposal_id: proposalId,
          mode: proposalMode,
          status: proposalStatus,
          ...(typeof entry?.session_id === "string" && entry.session_id
            ? { session_id: entry.session_id }
            : {}),
        }
      : null;

  const projectedState = projectedSession?.state;
  const projectedSessionId =
    typeof projectedSession?.session_id === "string"
      ? projectedSession.session_id
      : "";
  const projectedVersion = projectedSession?.state_version;
  const session =
    projectedSessionId &&
    typeof projectedState === "string" &&
    WPLUS_SOP_STATES.has(projectedState as WPlusSopState) &&
    typeof projectedVersion === "number"
      ? {
          session_id: projectedSessionId,
          title:
            typeof projectedSession?.title === "string"
              ? projectedSession.title
              : "W+ SOP 工作台",
          state: projectedState as WPlusSopState,
          state_version: projectedVersion,
          ...(typeof projectedSession?.last_event_kind === "string"
            ? { last_event_kind: projectedSession.last_event_kind }
            : {}),
        }
      : null;

  return { entryProposal, session };
}
