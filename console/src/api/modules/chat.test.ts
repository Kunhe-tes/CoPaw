import { beforeEach, describe, expect, it, vi } from "vitest";
import { request } from "../request";
import type { ChatHistory } from "../types";
import { chatApi } from "./chat";

vi.mock("../request", () => ({
  request: vi.fn(),
}));

describe("chatApi.getChat", () => {
  const chatId = "497fb716-5270-4214-aa2b-3bb227510a4e";

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("normalizes a 200 chat-not-found payload into a 404 error", async () => {
    const response = {
      detail: `Chat not found: ${chatId}`,
    };
    vi.mocked(request).mockResolvedValue(response);

    await expect(chatApi.getChat(chatId)).rejects.toMatchObject({
      message: response.detail,
      status: 404,
      data: response,
    });
  });

  it("preserves a valid chat history response", async () => {
    const response: ChatHistory = {
      chat: {
        id: chatId,
        session_id: "default:user-1",
        user_id: "user-1",
        channel: "default",
        name: "Test chat",
        created_at: null,
        updated_at: null,
      },
      messages: [{ role: "user", content: "hello" }],
      status: "idle",
    };
    vi.mocked(request).mockResolvedValue(response);

    await expect(chatApi.getChat(chatId)).resolves.toBe(response);
  });

  it("does not misclassify an unrelated detail response", async () => {
    const response = {
      detail: "Another successful response",
    };
    vi.mocked(request).mockResolvedValue(response);

    await expect(chatApi.getChat(chatId)).resolves.toBe(response);
  });
});
