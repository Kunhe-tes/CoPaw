import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("../request", () => ({ request: mocks.request }));
vi.mock("../config", () => ({
  getApiToken: () => "",
  getApiUrl: (path: string) => path,
}));
vi.mock("../authHeaders", () => ({ buildAuthHeaders: () => ({}) }));

describe("Goal delegation intent API", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each([false, true])(
    "sends explicit delegation enablement %s separately from Contract",
    async (enabled) => {
      const { chatApi } = await import("./chat");
      const contract = {
        objective: "Run work",
        completion_criteria: [],
        constraints: { must_preserve: [], must_not_do: [] },
        autonomy_boundary: "No deploy",
      };
      await chatApi.createGoal("chat-1", contract, enabled);
      expect(mocks.request).toHaveBeenCalledWith("/goals", {
        method: "POST",
        body: JSON.stringify({
          chat_id: "chat-1",
          contract,
          enable_subagents: enabled,
        }),
      });
    },
  );

  it.each([false, true])(
    "sends structured Steering delegation %s",
    async (enabled) => {
      const { chatApi } = await import("./chat");
      await chatApi.enqueueGoalSteering(
        "goal-1",
        "chat-1",
        "Continue",
        enabled,
      );
      expect(mocks.request).toHaveBeenCalledWith(
        "/goals/goal-1/steering?chat_id=chat-1",
        {
          method: "POST",
          body: JSON.stringify({
            content: "Continue",
            enable_subagents: enabled,
          }),
        },
      );
    },
  );
});
