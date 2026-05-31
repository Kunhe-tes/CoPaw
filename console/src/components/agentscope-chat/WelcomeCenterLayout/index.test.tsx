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

const mockedInputState = {
  disabled: false,
};

vi.mock("@agentscope-ai/icons", () => ({
  SparkAttachmentLine: () => <span data-testid="attachment-icon" />,
}));

vi.mock("@agentscope-ai/design", () => ({
  IconButton: () => <button type="button">upload</button>,
}));

vi.mock("@/components/agentscope-chat/ComposerQuickMenu", () => {
  const React = require("react");

  function ComposerQuickMenu(props: {
    children?: React.ReactNode;
    disabled?: boolean;
    triggerLabel: string;
  }) {
    const [open, setOpen] = React.useState(false);

    return (
      <div>
        <button
          type="button"
          aria-label={props.triggerLabel}
          disabled={props.disabled}
          onClick={() => {
            if (!props.disabled) {
              setOpen((prev: boolean) => !prev);
            }
          }}
        >
          menu
        </button>
        {open ? <div>{props.children}</div> : null}
      </div>
    );
  }

  function ComposerQuickMenuItem(props: { label: React.ReactNode }) {
    return <button type="button">{props.label}</button>;
  }

  return {
    __esModule: true,
    default: ComposerQuickMenu,
    ComposerQuickMenuItem,
  };
});

vi.mock("@/components/agentscope-chat", () => ({
  Attachments: ({ items }: { items: Array<{ name?: string }> }) => (
    <div>
      {items.map((item) => (
        <span key={item.name}>{item.name}</span>
      ))}
    </div>
  ),
  useChatAnywhereInput: (
    selector: (value: { disabled: boolean }) => unknown,
  ) => selector({ disabled: mockedInputState.disabled }),
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
  default: (props: { onFillInput?: (value: string) => void }) => (
    <div data-testid="featured-cases">
      <button type="button" onClick={() => props.onFillInput?.("案例提示")}>
        填充案例
      </button>
    </div>
  ),
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

describe("WelcomeCenterLayout", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedInputState.disabled = false;
    mockedUploadFile.mockResolvedValue({
      url: "demo.txt",
      file_name: "demo.txt",
    });
  });

  afterEach(() => {
    cleanup();
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

  it(
    "locks welcome composer interactions when the global input is disabled",
    async () => {
      const onSubmit = vi.fn();
      const file = new File(["hello"], "demo.txt", { type: "text/plain" });
      mockedInputState.disabled = true;

      render(<WelcomeCenterLayout greeting="你好" onSubmit={onSubmit} />);

      expect(screen.getByRole("textbox")).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "chat.quickMenu.trigger" }),
      ).toBeDisabled();
      expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();

      document.dispatchEvent(
        new CustomEvent("pasteFile", {
          detail: { file },
        }),
      );
      fireEvent.click(screen.getByRole("button", { name: "填充案例" }));

      expect(mockedUploadFile).not.toHaveBeenCalled();
      expect(screen.getByRole("textbox")).toHaveValue("");
      expect(onSubmit).not.toHaveBeenCalled();
    },
  );

  it("shows upload and custom quick actions in the same menu", async () => {
    render(
      <WelcomeCenterLayout
        greeting="你好"
        onSubmit={vi.fn()}
        quickMenuItems={[
          <button key="plan" type="button">
            Plan Mode
          </button>,
        ]}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "chat.quickMenu.trigger" }),
    );

    expect(screen.getByText("chat.quickMenu.upload")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Plan Mode" }),
    ).toBeInTheDocument();
  });

  it("renders prefix action items beside the quick menu in the welcome composer", () => {
    const { container } = render(
      <WelcomeCenterLayout
        greeting="你好"
        onSubmit={vi.fn()}
        prefixItems={
          <button type="button">
            计划模式
          </button>
        }
      />,
    );

    const actionButtons = Array.from(
      container.querySelectorAll(".welcome-input-actions button"),
    ).map((button) => button.textContent?.trim());

    expect(actionButtons).toContain("menu");
    expect(actionButtons).toContain("计划模式");
    expect(screen.getByRole("button", { name: "计划模式" })).toBeInTheDocument();
  });

  it("uses beforeSubmit to transform welcome submissions", async () => {
    const onSubmit = vi.fn();
    const beforeSubmit = vi.fn(async (data) => ({
      ...data,
      query: "transformed",
      biz_params: {
        mode: "plan",
      },
    }));

    render(
      <WelcomeCenterLayout
        greeting="你好"
        onSubmit={onSubmit}
        beforeSubmit={beforeSubmit}
      />,
    );

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "/plan draft" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      expect(beforeSubmit).toHaveBeenCalledWith({
        query: "/plan draft",
        fileList: [],
      });
      expect(onSubmit).toHaveBeenCalledWith({
        query: "transformed",
        fileList: [],
        biz_params: {
          mode: "plan",
        },
      });
    });
  });
});
