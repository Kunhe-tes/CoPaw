import { beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("../request", () => ({ request: mocks.request }));
describe("chat expert binding API", () => {
  beforeEach(() => vi.clearAllMocks());
  it("reads the binding using an encoded chat id", async () => {
    const { chatApi } = await import("./chat");
    await chatApi.getExpertBinding("chat/id 1");
    expect(mocks.request).toHaveBeenCalledWith(
      "/chats/chat%2Fid%201/expert-binding",
    );
  });
  it.each(["expert-1", null])(
    "preserves expert id %s and expected revision",
    async (expert_id) => {
      const { chatApi } = await import("./chat");
      await chatApi.updateExpertBinding("chat-1", {
        expected_revision: 7,
        expert_id,
      });
      expect(mocks.request).toHaveBeenCalledWith(
        "/chats/chat-1/expert-binding",
        {
          method: "PUT",
          body: JSON.stringify({ expected_revision: 7, expert_id }),
        },
      );
    },
  );
});
