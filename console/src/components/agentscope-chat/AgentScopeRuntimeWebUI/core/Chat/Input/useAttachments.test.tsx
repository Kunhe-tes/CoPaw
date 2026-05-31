import { act, render, renderHook, waitFor } from "@testing-library/react";
import type { UploadFile } from "antd";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import useAttachments from "./useAttachments";

const attachmentsSpy = vi.fn();

vi.mock("@agentscope-ai/icons", () => ({
  SparkAttachmentLine: () => null,
}));

vi.mock("@/components/agentscope-chat", () => ({
  Sender: {
    Header: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  },
  Attachments: (props: unknown) => {
    attachmentsSpy(props);
    return null;
  },
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
  beforeEach(() => {
    attachmentsSpy.mockClear();
  });

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

  it("passes disabled state to attachment list header", () => {
    const customRequest = vi.fn();
    const file = {
      uid: "uploaded-1",
      name: "demo.txt",
      status: "done",
    } satisfies UploadFile;
    const { result } = renderHook(() =>
      useAttachments(
        {
          customRequest,
        } as never,
        { disabled: true },
      ),
    );

    act(() => {
      result.current.setFileList([file]);
    });

    render(<>{result.current.uploadFileListHeader}</>);

    expect(attachmentsSpy).toHaveBeenCalledTimes(1);
    expect(attachmentsSpy.mock.calls[0]?.[0]).toMatchObject({
      disabled: true,
      items: [file],
    });
  });
});
