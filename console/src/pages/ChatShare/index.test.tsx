import { describe, expect, it } from "vitest";
import { prepareShareMessages } from "./shareView";

describe("ChatSharePage message preparation", () => {
  it("keeps structured cards and maps unknown cards to a read-only view", () => {
    const [message] = prepareShareMessages([
      {
        id: "turn-1",
        role: "assistant",
        cards: [
          { code: "AgentScopeRuntimeResponseCard", data: {} },
          { code: "ApprovalAction", data: { requestId: "approval-1" } },
          { code: "PlanInteraction", data: { planId: "plan-1" } },
          { code: "TaskRunGroupCard", data: { runId: "run-1" } },
          { code: "ResponseFeedback", data: { responseId: "response-1" } },
          { code: "UnknownCard", data: { value: "kept" } },
        ],
      },
    ] as never);
    expect(message.cards?.map((card) => card.code)).toEqual([
      "AgentScopeRuntimeResponseCard",
      "ApprovalAction",
      "PlanInteraction",
      "TaskRunGroupCard",
      "ResponseFeedback",
      "ReadOnlyStructuredCard",
    ]);
    expect(message.cards?.[message.cards.length - 1]?.data).toEqual({
      code: "UnknownCard",
      data: { value: "kept" },
    });
  });
});
