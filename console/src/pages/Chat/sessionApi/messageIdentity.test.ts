import { describe, expect, it } from "vitest";
import { convertMessages } from "./index";

describe("persisted history message identity", () => {
  it("reuses stable persisted IDs for user and assistant cards", () => {
    const messages = convertMessages([
      {
        id: "user-1",
        role: "user",
        content: [{ type: "text", text: "hello" }],
        timestamp: "2026-08-26T01:00:00Z",
      },
      {
        id: "assistant-1",
        role: "assistant",
        content: [{ type: "text", text: "world" }],
        timestamp: "2026-08-26T01:00:00Z",
      },
    ] as never);

    const repeated = convertMessages([
      {
        id: "user-1",
        role: "user",
        content: [{ type: "text", text: "hello" }],
        timestamp: "2026-08-26T01:00:00Z",
      },
      {
        id: "assistant-1",
        role: "assistant",
        content: [{ type: "text", text: "world" }],
        timestamp: "2026-08-26T01:00:00Z",
      },
    ] as never);

    expect(messages.map((message) => message.id)).toEqual(
      repeated.map((message) => message.id),
    );
    expect(messages[0].id).toBe("user-1");
    expect(messages[1].id).toContain("assistant-1");
  });
});
