import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Sidebar from "./Sidebar";

const iframeState = vi.hoisted(() => ({
  isSuperManager: false,
  manager: false,
  hideChat: false,
  source: "RMASSIST" as string | null,
}));

vi.mock(
  "@agentscope-ai/icons",
  () =>
    new Proxy(
      {},
      {
        get: (_, property) => (property === "then" ? undefined : () => null),
        has: () => true,
      },
    ),
);

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string | { defaultValue?: string }) =>
      typeof fallback === "string" ? fallback : fallback?.defaultValue || key,
  }),
}));

vi.mock("../api/modules/auth", () => ({
  authApi: {
    getStatus: vi.fn().mockResolvedValue({ enabled: false }),
  },
}));

vi.mock("../contexts/ThemeContext", () => ({
  useTheme: () => ({ isDark: false }),
}));

vi.mock("../hooks/useAppMessage", () => ({
  useAppMessage: () => ({ message: {} }),
}));

vi.mock("../stores/iframeStore", () => ({
  useIframeStore: (selector: (state: typeof iframeState) => unknown) =>
    selector(iframeState),
}));

afterEach(() => {
  cleanup();
  iframeState.source = "RMASSIST";
});

describe("Sidebar skill config visibility", () => {
  it("shows the skill config menu for the RMASSIST source", () => {
    render(
      <MemoryRouter>
        <Sidebar selectedKey="skill-config" />
      </MemoryRouter>,
    );

    expect(screen.getByText("Skill 配置")).toBeInTheDocument();
  });

  it("hides the skill config menu for other sources", () => {
    iframeState.source = "OTHER";

    render(
      <MemoryRouter>
        <Sidebar selectedKey="models" />
      </MemoryRouter>,
    );

    expect(screen.queryByText("Skill 配置")).not.toBeInTheDocument();
  });
});
