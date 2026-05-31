import { act, renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import useAttachments from "./useAttachments";

vi.mock("@agentscope-ai/icons", () => ({
  SparkAttachmentLine: () => null,
}));

vi.mock("@/components/agentscope-chat", () => ({
  Sender: {
    Header: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  },
  Attachments: () => null,
}));

vi.mock("@/components/agentscope-chat/ComposerQuickMenu", () => ({
  ComposerQuickMenuItem: () => null,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback: string) => fallback,
  }),
}));

describe("useAttachments", () => {
  it("does not upload pasted files when attachments are disabled", async () => {
    const customRequest = vi.fn();
    const file = new File(["hello"], "demo.txt", { type: "text/plain" });
    const { result } = renderHook(() =>
      useAttachments(
        {
          customRequest,
        } as never,
        { disabled: true },
      ),
    );

    act(() => {
      result.current.handlePasteFile?.(file);
    });

    await waitFor(() => {
      expect(result.current.fileList).toHaveLength(0);
    });
    expect(customRequest).not.toHaveBeenCalled();
  });
});
