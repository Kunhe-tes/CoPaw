import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Suggestions from "./Suggestions";
import { AgentScopeRuntimeRunStatus } from "../types";

const mocks = vi.hoisted(() => ({
  emit: vi.fn(),
  iframeSource: null as string | null,
}));

vi.mock("@/components/agentscope-chat", () => ({
  useProviderContext: () => ({
    getPrefixCls: (name: string) => `copaw-${name}`,
  }),
}));

vi.mock("../../Context/useChatAnywhereEventEmitter", () => ({
  emit: mocks.emit,
}));

vi.mock("@/stores/iframeStore", () => ({
  useIframeStore: (selector: (value: unknown) => unknown) =>
    selector({ source: mocks.iframeSource }),
}));

vi.mock("antd", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@agentscope-ai/icons", () => ({
  SparkRightArrowLine: () => null,
}));

vi.mock("./style", () => ({
  default: () => null,
}));

let root: Root | undefined;
let container: HTMLDivElement | undefined;

function renderSuggestions(status = AgentScopeRuntimeRunStatus.Completed) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root?.render(<Suggestions suggestions={["继续问什么"]} status={status} />);
  });
}

describe("Suggestions", () => {
  beforeEach(() => {
    mocks.emit.mockReset();
    mocks.iframeSource = null;
  });

  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    container?.remove();
    root = undefined;
    container = undefined;
  });

  it("emits suggestion submit event when clicked after completion", () => {
    renderSuggestions();

    const button = container?.querySelector("button");
    expect(button).not.toBeNull();

    act(() => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(mocks.emit).toHaveBeenCalledWith({
      type: "handleSuggestionSubmit",
      data: { query: "继续问什么", fileList: [] },
    });
  });

  it("does not submit while response is still generating", () => {
    renderSuggestions(AgentScopeRuntimeRunStatus.InProgress);

    const button = container?.querySelector("button");
    act(() => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(mocks.emit).not.toHaveBeenCalled();
  });

  it("does not render suggestions when source is ruice", () => {
    mocks.iframeSource = "ruice";

    renderSuggestions();

    expect(container?.querySelector("button")).toBeNull();
    expect(container?.textContent).not.toContain("猜你想问");
  });
});
