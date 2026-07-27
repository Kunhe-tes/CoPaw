import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("../request", () => ({ request: mocks.request }));

import { hookManagementApi } from "./hookManagement";

describe("hookManagementApi", () => {
  beforeEach(() => {
    mocks.request.mockReset();
    mocks.request.mockResolvedValue({});
  });

  it("saves the complete Hook draft with its optimistic-lock revision", async () => {
    const hooks = { enabled: true, events: {} };

    await hookManagementApi.saveConfiguration(hooks, "rev-1");

    expect(mocks.request).toHaveBeenCalledWith(
      "/hook-management/configuration",
      {
        method: "PUT",
        headers: { "If-Match": "rev-1" },
        body: JSON.stringify({ hooks }),
      },
    );
  });

  it("uploads files and overwrite names as multipart data", async () => {
    const file = new File(["echo ok"], "guard.sh", { type: "text/plain" });

    await hookManagementApi.uploadScripts([file], ["guard.sh"]);

    const [, options] = mocks.request.mock.calls[0] as [
      string,
      { method: string; body: FormData },
    ];
    expect(options.method).toBe("POST");
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.body.getAll("files")).toEqual([file]);
    expect(options.body.get("overwrite")).toBe('["guard.sh"]');
  });

  it("confirms real execution when submitting a manual test", async () => {
    const handler = {
      id: "guard-shell",
      type: "command" as const,
      argv: ["echo"],
    };
    const context = { hook_event_name: "PreToolUse" };

    await hookManagementApi.manualTest(handler, context);

    expect(mocks.request).toHaveBeenCalledWith("/hook-management/manual-test", {
      method: "POST",
      body: JSON.stringify({
        confirmRealExecution: true,
        handler,
        context,
      }),
    });
  });
});
