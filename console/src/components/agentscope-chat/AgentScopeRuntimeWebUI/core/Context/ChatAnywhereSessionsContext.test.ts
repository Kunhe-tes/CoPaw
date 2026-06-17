import { describe, expect, it } from "vitest";
import { mergeRecoveredSessionIntoList } from "./ChatAnywhereSessionsContext";

describe("mergeRecoveredSessionIntoList", () => {
  it("prepends a recovered detail session when it is absent from context state", () => {
    const sessions = [
      {
        id: "chat-visible",
        name: "visible",
        messages: [],
      },
    ];
    const recovered = {
      id: "chat-deep-link",
      name: "deep link",
      messages: [],
    };

    expect(mergeRecoveredSessionIntoList(sessions, recovered)).toEqual([
      recovered,
      ...sessions,
    ]);
  });

  it("keeps the current list reference when the recovered session already exists", () => {
    const sessions = [
      {
        id: "local-1",
        realId: "chat-real-1",
        name: "pending",
        messages: [],
      },
    ];
    const recovered = {
      id: "chat-real-1",
      name: "real",
      messages: [],
    };

    expect(mergeRecoveredSessionIntoList(sessions, recovered)).toBe(sessions);
  });
});
