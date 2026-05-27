import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { UploadFile } from "antd";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Input from "./index";
import { RUNTIME_INPUT_SET_CONTENT_EVENT } from "../hooks/followUpSubmit";

const attachmentState = {
  currentFileList: [] as UploadFile[],
  getFileList: vi.fn<() => UploadFile[]>(),
  setFileList: vi.fn((next: UploadFile[]) => {
    attachmentState.currentFileList = next;
  }),
  handlePasteFile: vi.fn<(file: File) => void>(),
  handleUploadMenuClick: vi.fn<() => void>(),
};

vi.mock("@/components/agentscope-chat", () => ({
  ChatInput: (props: {
    value?: string;
    onChange?: (value: string) => void;
    onSubmit?: () => void;
    prefix?: React.ReactNode;
  }) => (
    <div>
      <input
        data-testid="chat-input"
        value={props.value || ""}
        onChange={(event) => props.onChange?.(event.target.value)}
      />
      <div data-testid="chat-prefix">{props.prefix}</div>
      <button type="button" onClick={() => props.onSubmit?.()}>
        submit
      </button>
    </div>
  ),
  Disclaimer: () => null,
  useProviderContext: () => ({
    getPrefixCls: (prefix: string) => prefix,
  }),
}));

vi.mock("../../Context/ChatAnywhereOptionsContext", () => ({
  useChatAnywhereOptions: (
    selector: (value: { sender: Record<string, unknown> }) => unknown,
  ) => selector({ sender: senderOptions.current }),
}));

const senderOptions = {
  current: {} as Record<string, unknown>,
};

vi.mock("../../Context/ChatAnywhereInputContext", () => ({
  useChatAnywhereInput: (
    selector: (value: { disabled: boolean; loading: boolean }) => unknown,
  ) => selector({ disabled: false, loading: false }),
}));

vi.mock("./useAttachments", () => ({
  default: () => ({
    fileList: attachmentState.currentFileList,
    getFileList: attachmentState.getFileList,
    setFileList: attachmentState.setFileList,
    handlePasteFile: attachmentState.handlePasteFile,
    uploadQuickMenuItem: (
      <button type="button" onClick={() => attachmentState.handleUploadMenuClick()}>
        上传文件
      </button>
    ),
    uploadFileListHeader: null,
  }),
}));

describe("Chat Input restore flow", () => {
  beforeEach(() => {
    senderOptions.current = {};
    attachmentState.currentFileList = [];
    attachmentState.getFileList.mockImplementation(
      () => attachmentState.currentFileList,
    );
    attachmentState.getFileList.mockClear();
    attachmentState.setFileList.mockClear();
    attachmentState.handlePasteFile.mockClear();
    attachmentState.handleUploadMenuClick.mockClear();
  });

  afterEach(() => {
    cleanup();
  });

  it("restores attachments and biz_params when follow-up auto-submit fails", async () => {
    const onSubmit = vi.fn();
    const restoredFiles = [
      {
        uid: "restored-file",
        name: "demo.txt",
        response: { url: "/demo.txt" },
      },
    ] as UploadFile[];
    const biz_params = {
      user_prompt_params: {
        source: "follow-up",
      },
    };

    render(<Input onCancel={vi.fn()} onSubmit={onSubmit} />);

    document.dispatchEvent(
      new CustomEvent(RUNTIME_INPUT_SET_CONTENT_EVENT, {
        detail: {
          content: "recover me",
          fileList: restoredFiles,
          biz_params,
        },
      }),
    );

    await waitFor(() => {
      expect((screen.getByTestId("chat-input") as HTMLInputElement).value).toBe(
        "recover me",
      );
    });
    expect(attachmentState.setFileList).toHaveBeenCalledWith(restoredFiles);

    fireEvent.click(
      screen.getByRole("button", { name: "submit", hidden: true }),
    );

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        query: "recover me",
        fileList: restoredFiles,
        biz_params,
      });
    });
    expect(attachmentState.setFileList).toHaveBeenLastCalledWith([]);
  });

  it("clears restored biz_params when input content is replaced programmatically", async () => {
    const onSubmit = vi.fn();
    const biz_params = {
      user_prompt_params: {
        source: "follow-up",
      },
    };

    render(<Input onCancel={vi.fn()} onSubmit={onSubmit} />);

    document.dispatchEvent(
      new CustomEvent(RUNTIME_INPUT_SET_CONTENT_EVENT, {
        detail: {
          content: "recover me",
          biz_params,
        },
      }),
    );

    document.dispatchEvent(
      new CustomEvent(RUNTIME_INPUT_SET_CONTENT_EVENT, {
        detail: {
          content: "normal prompt",
        },
      }),
    );

    await waitFor(() => {
      expect((screen.getByTestId("chat-input") as HTMLInputElement).value).toBe(
        "normal prompt",
      );
    });

    fireEvent.click(
      screen.getByRole("button", { name: "submit", hidden: true }),
    );

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        query: "normal prompt",
        fileList: [],
        biz_params: undefined,
      });
    });
  });

  it("clears restored biz_params after the user edits the recovered content", async () => {
    const onSubmit = vi.fn();
    const biz_params = {
      user_prompt_params: {
        source: "follow-up",
      },
    };

    render(<Input onCancel={vi.fn()} onSubmit={onSubmit} />);

    document.dispatchEvent(
      new CustomEvent(RUNTIME_INPUT_SET_CONTENT_EVENT, {
        detail: {
          content: "recover me",
          biz_params,
        },
      }),
    );

    fireEvent.change(screen.getByTestId("chat-input"), {
      target: { value: "another question" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "submit", hidden: true }),
    );

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        query: "another question",
        fileList: [],
        biz_params: undefined,
      });
    });
  });

  it("handles files dispatched by the chat drag-and-drop bridge", async () => {
    const file = new File(["hello"], "demo.txt", { type: "text/plain" });

    render(<Input onCancel={vi.fn()} onSubmit={vi.fn()} />);

    document.dispatchEvent(
      new CustomEvent("pasteFile", {
        detail: { file },
      }),
    );

    expect(attachmentState.handlePasteFile).toHaveBeenCalledWith(file);
  });

  it("allows beforeSubmit to inspect and transform the submitted input", async () => {
    const onSubmit = vi.fn();
    senderOptions.current = {
      beforeSubmit: vi.fn(async (data) => ({
        ...data,
        query: "transformed",
        biz_params: {
          ...(data.biz_params || {}),
          mode: "plan",
        },
      })),
    };

    render(<Input onCancel={vi.fn()} onSubmit={onSubmit} />);

    fireEvent.change(screen.getByTestId("chat-input"), {
      target: { value: "/plan transformed" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "submit", hidden: true }),
    );

    await waitFor(() => {
      expect(senderOptions.current.beforeSubmit).toHaveBeenCalledWith({
        query: "/plan transformed",
        fileList: [],
        biz_params: undefined,
      });
      expect(onSubmit).toHaveBeenCalledWith({
        query: "transformed",
        fileList: [],
        biz_params: { mode: "plan" },
      });
    });
  });

  it("allows beforeSubmit to clear input without submitting a request", async () => {
    const onSubmit = vi.fn();
    senderOptions.current = {
      beforeSubmit: vi.fn(async () => ({
        shouldSubmit: false,
        clearInput: true,
      })),
    };

    render(<Input onCancel={vi.fn()} onSubmit={onSubmit} />);

    fireEvent.change(screen.getByTestId("chat-input"), {
      target: { value: "/plan" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "submit", hidden: true }),
    );

    await waitFor(() => {
      expect(onSubmit).not.toHaveBeenCalled();
      expect((screen.getByTestId("chat-input") as HTMLInputElement).value).toBe(
        "",
      );
    });
  });

  it("shows upload and custom quick actions inside the plus menu", async () => {
    const onPlanModeClick = vi.fn();
    senderOptions.current = {
      quickMenuItems: [
        <button key="plan" type="button" onClick={onPlanModeClick}>
          计划模式
        </button>,
      ],
    };

    render(<Input onCancel={vi.fn()} onSubmit={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "快捷操作", hidden: true }));

    fireEvent.click(
      await screen.findByRole("button", { name: "上传文件", hidden: true }),
    );
    fireEvent.click(screen.getByRole("button", { name: "快捷操作", hidden: true }));
    fireEvent.click(
      await screen.findByRole("button", { name: "计划模式", hidden: true }),
    );

    expect(attachmentState.handleUploadMenuClick).toHaveBeenCalledTimes(1);
    expect(onPlanModeClick).toHaveBeenCalledTimes(1);
  });
});
