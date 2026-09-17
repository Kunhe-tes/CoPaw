import { describe, expect, it } from "vitest";

import { readWPlusSopChatProjection } from "./wplusSopEntryEvents";

describe("readWPlusSopChatProjection", () => {
  it("restores pending entry and persisted session projections from Chat metadata", () => {
    expect(
      readWPlusSopChatProjection({
        wplus_sop_entry_proposal: {
          proposal_id: "proposal-1",
          mode: "implicit",
          status: "pending",
          session_id: "sop-from-entry",
        },
        wplus_sop_session: {
          session_id: "sop-1",
          title: "客户经营 SOP",
          state: "Paused",
          state_version: 9,
          last_event_kind: "session_state_changed",
        },
      }),
    ).toEqual({
      entryProposal: {
        proposal_id: "proposal-1",
        mode: "implicit",
        status: "pending",
        session_id: "sop-from-entry",
      },
      session: {
        session_id: "sop-1",
        title: "客户经营 SOP",
        state: "Paused",
        state_version: 9,
        last_event_kind: "session_state_changed",
      },
    });
  });

  it("ignores malformed or unknown metadata without inventing controls", () => {
    expect(
      readWPlusSopChatProjection({
        wplus_sop_entry_proposal: {
          proposal_id: "proposal-1",
          mode: "unknown",
          status: "pending",
        },
        wplus_sop_session: {
          session_id: "sop-1",
          state: "UnknownState",
          state_version: "9",
        },
      }),
    ).toEqual({ entryProposal: null, session: null });
  });
});
