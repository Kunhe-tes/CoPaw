import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ChatAnywhereI18nContextProvider,
  type Locale,
} from "../../Context/ChatAnywhereI18nContext";
import Error from "./Error";

const mocks = vi.hoisted(() => ({
  copy: vi.fn(async (text: string) => {
    void text;
  }),
}));

vi.mock("@/components/agentscope-chat", () => ({
  Bubble: {
    Interrupted: ({ title, desc }: { title?: string; desc?: string }) => (
      <div data-testid="interrupted">
        {title} {desc}
      </div>
    ),
  },
  useProviderContext: () => ({
    getPrefixCls: (name: string) => `swe-${name}`,
  }),
}));

vi.mock("@/components/agentscope-chat/Util/copy", () => ({
  copy: mocks.copy,
}));

vi.mock("@agentscope-ai/icons", () => ({
  SparkCopyLine: () => <span data-testid="copy-icon" />,
  SparkDownLine: () => <span data-testid="down-icon" />,
  SparkErrorCircleLine: () => <span data-testid="error-icon" />,
  SparkRightArrowLine: () => <span data-testid="right-icon" />,
  SparkUpLine: () => <span data-testid="up-icon" />,
}));

const providerError = {
  code: "model_call_failed",
  message:
    'The model provider returned an error status (401). {"error":{"code":"invalid_api_key","message":"Invalid access token or token expired","param":null,"type":"invalid_request_error"},"request_id":"982f9613-d43f-9c9a-b518-abcf1f2ed95"}',
};

function renderError(locale: Locale = "cn") {
  return render(
    <ChatAnywhereI18nContextProvider defaultLocale={locale}>
      <MemoryRouter>
        <Error data={providerError} />
      </MemoryRouter>
    </ChatAnywhereI18nContextProvider>,
  );
}

describe("model call failed card", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mocks.copy.mockClear();
  });

  it("shows localized recovery guidance with details collapsed by default", () => {
    renderError();

    expect(screen.getByText("模型连接失败")).toBeInTheDocument();
    expect(screen.getByText("HTTP 401")).toBeInTheDocument();
    expect(
      screen.getByText("当前模型的访问凭证无效或已过期，暂时无法生成回复。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开模型设置" })).toHaveAttribute(
      "href",
      "/models",
    );
    expect(
      screen.getByRole("button", { name: "详细报错信息" }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "复制错误信息" })).toBeNull();
    expect(screen.queryByRole("button", { name: "重试" })).toBeNull();
    expect(screen.getByText("invalid_api_key")).not.toBeVisible();
  });

  it("renders the complete card in English when the runtime locale is English", () => {
    renderError("en");

    expect(screen.getByText("Model connection failed")).toBeInTheDocument();
    expect(
      screen.getByText(
        "The current model credentials are invalid or expired, so a response could not be generated.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open model settings" }),
    ).toHaveAttribute("href", "/models");
    expect(
      screen.getByRole("button", { name: "Error details" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("reveals structured details and copies only the diagnostic text", async () => {
    renderError();

    fireEvent.click(screen.getByRole("button", { name: "详细报错信息" }));

    expect(screen.getByText("invalid_api_key")).toBeInTheDocument();
    expect(
      screen.getByText("Invalid access token or token expired"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("982f9613-d43f-9c9a-b518-abcf1f2ed95"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "复制错误信息" }));

    await waitFor(() => expect(mocks.copy).toHaveBeenCalledOnce());
    expect(mocks.copy.mock.calls[0][0]).toContain("HTTP 状态: 401");
    expect(mocks.copy.mock.calls[0][0]).toContain("错误类型: invalid_api_key");
    expect(screen.getByText("已复制")).toBeInTheDocument();
  });

  it("keeps the existing interrupted component for other errors", () => {
    render(
      <MemoryRouter>
        <Error data={{ code: "stream_error", message: "network failed" }} />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("interrupted")).toHaveTextContent(
      "stream_error network failed",
    );
  });
});
