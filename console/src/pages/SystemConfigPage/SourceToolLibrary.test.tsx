import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SourceToolLibrary } from "./SourceToolLibrary";

const mocks = vi.hoisted(() => ({
  listEffective: vi.fn(),
  listDrafts: vi.fn(),
  uploadDraft: vi.fn(),
  publishDraft: vi.fn(),
  manualTest: vi.fn(),
}));

vi.mock("@/api/modules/sourceTools", () => ({
  sourceToolsApi: {
    listEffective: mocks.listEffective,
    listDrafts: mocks.listDrafts,
    uploadDraft: mocks.uploadDraft,
    publishDraft: mocks.publishDraft,
    manualTest: mocks.manualTest,
    discardDraft: vi.fn(),
    deactivate: vi.fn(),
    history: vi.fn(),
    audit: vi.fn(),
    downloadVersion: vi.fn(),
  },
}));

vi.mock("@/hooks/useAppMessage", () => ({
  useAppMessage: () => ({
    message: { success: vi.fn(), error: vi.fn() },
  }),
}));

describe("SourceToolLibrary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listEffective.mockResolvedValue([]);
    mocks.listDrafts.mockResolvedValue([
      {
        name: "source_echo",
        description: "Echo source input.",
        json_schema: { type: "object" },
        required_env: [],
        content_digest: "1234567890abcdef",
        created_at: 1,
        created_by: "manager",
        status: "draft",
      },
    ]);
  });

  it("loads drafts and requires explicit confirmation before a manual test", async () => {
    render(<SourceToolLibrary sourceId="portal" />);

    expect(await screen.findByText("source_echo")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "手动测试" }));

    expect(await screen.findByText("测试会产生真实副作用")).toBeTruthy();
    expect(mocks.manualTest).not.toHaveBeenCalled();
  });

  it("submits a JSON object only after the manual-test confirmation", async () => {
    mocks.manualTest.mockResolvedValue({ output: { ok: true } });
    render(<SourceToolLibrary sourceId="portal" />);

    fireEvent.click(await screen.findByRole("button", { name: "手动测试" }));
    fireEvent.change(screen.getByLabelText("JSON 输入"), {
      target: { value: '{"id":"42"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认执行" }));

    await waitFor(() => {
      expect(mocks.manualTest).toHaveBeenCalledWith("source_echo", {
        id: "42",
      });
    });
  });
});
