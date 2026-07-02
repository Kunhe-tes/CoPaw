import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  openDistributeModal: vi.fn(),
  closeDistributeModal: vi.fn(),
  fetchConfig: vi.fn(),
  handleSave: vi.fn(),
  handleLanguageChange: vi.fn(),
  handleTimezoneChange: vi.fn(),
}));

vi.mock("@agentscope-ai/design", () => {
  const Button = ({
    children,
    icon,
    ...props
  }: React.PropsWithChildren<{
    icon?: React.ReactNode;
    [key: string]: unknown;
  }>) => (
    <button type="button" {...props}>
      {icon}
      {children}
    </button>
  );
  const Form = Object.assign(
    ({ children }: React.PropsWithChildren) => <form>{children}</form>,
    {
      useWatch: () => undefined,
    },
  );
  const Tooltip = ({ children }: React.PropsWithChildren) => <>{children}</>;
  return { Button, Form, Tooltip };
});

vi.mock("@ant-design/icons", () => ({
  SendOutlined: () => <span data-testid="send-icon" />,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock("@/components/PageHeader", () => ({
  PageHeader: ({ current }: { current: string }) => <h1>{current}</h1>,
}));

vi.mock("./useAgentConfig.tsx", () => ({
  useAgentConfig: () => ({
    form: {},
    loading: false,
    saving: false,
    error: null,
    language: "zh",
    savingLang: false,
    timezone: "UTC",
    savingTimezone: false,
    fetchConfig: mocks.fetchConfig,
    handleSave: mocks.handleSave,
    handleLanguageChange: mocks.handleLanguageChange,
    handleTimezoneChange: mocks.handleTimezoneChange,
    distributeModalOpen: false,
    currentConfigGroup: "",
    currentConfigGroupLabel: "",
    openDistributeModal: mocks.openDistributeModal,
    closeDistributeModal: mocks.closeDistributeModal,
    canDistribute: true,
  }),
}));

vi.mock("./components", () => {
  const card =
    (label: string) =>
    ({ extra }: { extra?: React.ReactNode }) => (
      <section>
        <h2>{label}</h2>
        {extra}
      </section>
    );
  return {
    ReactAgentCard: card("React Agent 配置"),
    LlmRetryCard: card("LLM 重试配置"),
    QueryRetryCard: card("Query 重试配置"),
    LlmRateLimiterCard: card("LLM 限流配置"),
    ContextCompactCard: card("上下文压缩配置"),
    ToolResultCompactCard: card("工具结果压缩配置"),
    MemorySummaryCard: card("记忆摘要配置"),
    EmbeddingConfigCard: card("Embedding 配置"),
    DistributeModal: () => null,
  };
});

import AgentConfigPage from "./index";

describe("AgentConfigPage", () => {
  it("does not render embedding or tool result compaction configuration entries", () => {
    render(<AgentConfigPage />);

    expect(screen.getByText("Query 重试配置")).toBeTruthy();
    expect(screen.getByText("LLM 限流配置")).toBeTruthy();
    expect(screen.queryByText("工具结果压缩配置")).toBeNull();
    expect(screen.queryByText("Embedding 配置")).toBeNull();
  });
});
