import type React from "react";
import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import type { UploadFile } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ComposerQuickMenu from "@/components/agentscope-chat/ComposerQuickMenu";
import useAttachments from "./useAttachments";
import quickMenuStyles from "@/components/agentscope-chat/ComposerQuickMenu/index.module.less";

const attachmentsSpy = vi.fn();
const quickMenuItemSpy = vi.fn();

vi.mock("@agentscope-ai/icons", () => ({
  SparkAttachmentLine: () => null,
}));

vi.mock("@agentscope-ai/design", () => ({
  IconButton: () => null,
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

vi.mock(
  "@/components/agentscope-chat/ComposerQuickMenu",
  async (importOriginal) => {
    const actual = await importOriginal<
      typeof import("@/components/agentscope-chat/ComposerQuickMenu")
    >();
    return {
      ...actual,
      ComposerQuickMenuItem: (props: unknown) => {
        quickMenuItemSpy(props);
        return <div>{(props as { label: React.ReactNode }).label}</div>;
      },
    };
  },
);

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback: string) => fallback,
  }),
}));

describe("useAttachments", () => {
  beforeEach(() => {
    attachmentsSpy.mockClear();
    quickMenuItemSpy.mockClear();
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

  it("marks the default upload quick menu item as interactive", () => {
    const { result } = renderHook(() =>
      useAttachments({
        customRequest: vi.fn(),
      }),
    );

    render(<>{result.current.uploadQuickMenuItem}</>);

    expect(quickMenuItemSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        interactive: true,
        label: "上传文件",
      }),
    );
  });

  it("renders the upload trigger at the same full row width as other quick menu items", () => {
    const { result } = renderHook(() =>
      useAttachments({
        customRequest: vi.fn(),
      }),
    );

    const uploadItem = result.current.uploadQuickMenuItem as React.ReactElement;

    expect(quickMenuStyles.uploadTrigger).toEqual(expect.any(String));
    expect(uploadItem.props.className).toBe(quickMenuStyles.uploadTrigger);
  });

  it("keeps the uploader mounted until a file is selected, then closes the quick menu", async () => {
    const customRequest = vi.fn();
    const { result } = renderHook(() => useAttachments({ customRequest }));

    render(
      <ComposerQuickMenu triggerLabel="快捷操作">
        {result.current.uploadQuickMenuItem}
      </ComposerQuickMenu>,
    );

    fireEvent.click(screen.getByRole("button", { name: "快捷操作" }));
    const fileInputs = Array.from(
      document.querySelectorAll<HTMLInputElement>(
        ".ant-upload input[type=file]",
      ),
    );
    const fileInput = fileInputs[fileInputs.length - 1];

    expect(fileInput).not.toBeNull();
    const uploadLabels = screen.getAllByText("上传文件");
    fireEvent.click(uploadLabels[uploadLabels.length - 1]);
    expect(fileInput).toBeInTheDocument();

    fireEvent.change(fileInput!, {
      target: {
        files: [new File(["hello"], "demo.txt", { type: "text/plain" })],
      },
    });

    await waitFor(() => {
      expect(customRequest).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(
        document.querySelector(`.${quickMenuStyles.panel}`),
      ).not.toBeInTheDocument();
    });
  });

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
      result.current.handlePasteFile?.(file);
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
