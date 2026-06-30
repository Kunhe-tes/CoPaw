import type React from "react";
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import useAttachments from "./useAttachments";

vi.mock("@agentscope-ai/icons", () => ({
  SparkAttachmentLine: () => null,
}));

vi.mock("@agentscope-ai/design", () => ({
  IconButton: () => null,
}));

vi.mock("@/components/agentscope-chat", () => ({
  Attachments: () => null,
  Sender: {
    Header: ({ children }: { children?: React.ReactNode }) => children,
  },
}));

describe("useAttachments", () => {
  it("routes pasted files to customRequest even when they do not match the picker accept hint", () => {
    const customRequest = vi.fn();
    const file = new File(["echo hello"], "run.sh", {
      type: "text/x-shellscript",
    });

    const { result } = renderHook(() =>
      useAttachments({
        accept: "image/*,.txt",
        customRequest,
      }),
    );

    act(() => {
      result.current.handlePasteFile(file);
    });

    expect(customRequest).toHaveBeenCalledTimes(1);
    expect(customRequest.mock.calls[0][0]).toMatchObject({
      file,
      filename: "file",
      action: "",
      method: "POST",
    });
  });
});
