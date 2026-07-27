import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import WelcomeCenterLayout from "./index";
import { chatApi } from "@/api/modules/chat";

vi.mock("@agentscope-ai/icons", () => ({
  SparkAttachmentLine: () => <span data-testid="attachment-icon" />,
}));

vi.mock("@agentscope-ai/design", () => ({
  IconButton: () => <button type="button">upload</button>,
}));

vi.mock("@/components/agentscope-chat", () => ({
  Attachments: ({ items }: { items: Array<{ name?: string }> }) => (
    <div>
      {items.map((item) => (
        <span key={item.name}>{item.name}</span>
      ))}
    </div>
  ),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock("@/api/modules/chat", () => ({
  chatApi: {
    uploadFile: vi.fn(),
    filePreviewUrl: vi.fn((filename: string) => `/preview/${filename}`),
  },
}));

vi.mock("../FeaturedCases", () => ({
  default: () => <div data-testid="featured-cases" />,
}));

vi.mock("../CaseDetailDrawer", () => ({
  default: () => null,
}));

vi.mock("@/api/modules/featuredCases", () => ({
  featuredCasesApi: {
    getCaseDetail: vi.fn(),
  },
}));

const mockedUploadFile = vi.mocked(chatApi.uploadFile);
const skills = [
  { name: "browser", description: "Use a browser" },
  { name: "Build", description: "Build an app" },
];

describe("WelcomeCenterLayout", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    mockedUploadFile.mockResolvedValue({
      url: "demo.txt",
      file_name: "demo.txt",
    });
  });

  it("handles files dispatched by the chat drag-and-drop bridge", async () => {
    const file = new File(["hello"], "demo.txt", { type: "text/plain" });

    render(<WelcomeCenterLayout greeting="你好" onSubmit={vi.fn()} />);

    document.dispatchEvent(
      new CustomEvent("pasteFile", {
        detail: { file },
      }),
    );

    expect(mockedUploadFile).toHaveBeenCalledWith(file);
    await waitFor(() => {
      expect(screen.getByText("demo.txt")).toBeInTheDocument();
    });
  });

  it("opens the shared labelled skill menu and selects a matching skill by click", () => {
    const onChange = vi.fn();

    render(
      <WelcomeCenterLayout
        greeting="你好"
        onSubmit={vi.fn()}
        skillMentions={{
          items: skills,
          selected: [],
          onOpen: vi.fn(),
          onChange,
        }}
      />,
    );

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "请用 @br" } });

    expect(screen.getByRole("group", { name: "可用技能" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /browser/ }));

    expect(onChange).toHaveBeenCalledWith(["browser"]);
    expect(input).toHaveValue("请用  ");
  });

  it("selects a matching skill with Enter without submitting", () => {
    const onChange = vi.fn();
    const onSubmit = vi.fn();

    render(
      <WelcomeCenterLayout
        greeting="你好"
        onSubmit={onSubmit}
        skillMentions={{
          items: skills,
          selected: [],
          onOpen: vi.fn(),
          onChange,
        }}
      />,
    );

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "@BU" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onChange).toHaveBeenCalledWith(["Build"]);
    expect(onSubmit).not.toHaveBeenCalled();
    expect(input).toHaveValue(" ");
  });

  it("does not submit while a loading skill menu is open", () => {
    const onSubmit = vi.fn();

    render(
      <WelcomeCenterLayout
        greeting="你好"
        onSubmit={onSubmit}
        skillMentions={{
          items: [],
          selected: [],
          loading: true,
          onOpen: vi.fn(),
          onChange: vi.fn(),
        }}
      />,
    );

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "@missing" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onSubmit).not.toHaveBeenCalled();
    expect(input).toHaveValue("@missing");
  });

  it("removes selected skill tags through the shared tag control", () => {
    const onChange = vi.fn();

    render(
      <WelcomeCenterLayout
        greeting="你好"
        onSubmit={vi.fn()}
        skillMentions={{
          items: skills,
          selected: ["browser"],
          onOpen: vi.fn(),
          onChange,
        }}
      />,
    );

    expect(screen.getByText("@browser")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Close"));

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("awaits beforeSubmit before sending and clearing the welcome input", async () => {
    const onSubmit = vi.fn();
    let resolveBeforeSubmit!: (result: boolean) => void;
    const beforeSubmit = vi.fn(
      () =>
        new Promise<boolean>((resolve) => {
          resolveBeforeSubmit = resolve;
        }),
    );

    render(
      <WelcomeCenterLayout
        greeting="你好"
        onSubmit={onSubmit}
        beforeSubmit={beforeSubmit}
      />,
    );

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(beforeSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
    expect(input).toHaveValue("hello");

    resolveBeforeSubmit(true);

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({ query: "hello", fileList: [] });
      expect(input).toHaveValue("");
    });
  });

  it("does not submit or clear the welcome input when beforeSubmit returns false", async () => {
    const onSubmit = vi.fn();
    const beforeSubmit = vi.fn().mockResolvedValue(false);

    render(
      <WelcomeCenterLayout
        greeting="你好"
        onSubmit={onSubmit}
        beforeSubmit={beforeSubmit}
      />,
    );

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => expect(beforeSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(input).toHaveValue("hello");
  });

  it("prevents duplicate sends while beforeSubmit is pending", async () => {
    const onSubmit = vi.fn();
    let resolveBeforeSubmit!: (result: boolean) => void;
    const beforeSubmit = vi.fn(
      () =>
        new Promise<boolean>((resolve) => {
          resolveBeforeSubmit = resolve;
        }),
    );

    render(
      <WelcomeCenterLayout
        greeting="你好"
        onSubmit={onSubmit}
        beforeSubmit={beforeSubmit}
      />,
    );

    const input = screen.getByRole("textbox");
    const sendButton = screen.getByRole("button", { name: "发送" });
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.click(sendButton);
    fireEvent.click(sendButton);

    expect(beforeSubmit).toHaveBeenCalledTimes(1);
    expect(input).toBeDisabled();
    expect(sendButton).toBeDisabled();

    resolveBeforeSubmit(true);

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });
  });

  it("does not submit or clear attachments that finish uploading during preflight", async () => {
    const onSubmit = vi.fn();
    let resolveBeforeSubmit!: (result: boolean) => void;
    let resolveUpload!: (result: { url: string; file_name: string }) => void;
    const beforeSubmit = vi.fn(
      () =>
        new Promise<boolean>((resolve) => {
          resolveBeforeSubmit = resolve;
        }),
    );
    mockedUploadFile.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveUpload = resolve;
        }),
    );

    render(
      <WelcomeCenterLayout
        greeting="你好"
        onSubmit={onSubmit}
        beforeSubmit={beforeSubmit}
      />,
    );

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    const file = new File(["hello"], "later.txt", { type: "text/plain" });
    document.dispatchEvent(
      new CustomEvent("pasteFile", {
        detail: { file },
      }),
    );
    await waitFor(() =>
      expect(screen.getByText("later.txt")).toBeInTheDocument(),
    );

    resolveUpload({ url: "later.txt", file_name: "later.txt" });
    await waitFor(() =>
      expect(chatApi.filePreviewUrl).toHaveBeenCalledWith("later.txt"),
    );

    resolveBeforeSubmit(true);
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({ query: "hello", fileList: [] });
      expect(screen.getByText("later.txt")).toBeInTheDocument();
    });
  });
});
