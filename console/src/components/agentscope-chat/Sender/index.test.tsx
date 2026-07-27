import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Sender from "./index";

vi.mock("@/components/agentscope-chat", () => ({
  useProviderContext: () => ({
    direction: "ltr",
    getPrefixCls: (prefix: string) => prefix,
  }),
}));

vi.mock("./SenderHeader", () => ({
  default: () => null,
  SendHeaderContext: {
    Provider: ({ children }: { children: React.ReactNode }) => children,
  },
}));

vi.mock("./ModeSelect", () => ({ default: () => null }));
vi.mock("./BeforeUIContainer", () => ({ default: () => null }));
vi.mock("./components/ActionButton", () => ({
  ActionButtonContext: {
    Provider: ({ children }: { children: React.ReactNode }) => children,
  },
}));
vi.mock("./components/ClearButton", () => ({ default: () => null }));
vi.mock("./components/LoadingButton", () => ({ default: () => null }));
vi.mock("./components/SendButton", () => ({ default: () => null }));

const skills = [
  { name: "browser", description: "Use a browser" },
  { name: "Build", description: "Build an app" },
];

function renderSender() {
  const onOpen = vi.fn();
  const onChange = vi.fn();

  render(
    <Sender
      skillMentions={{
        items: skills,
        selected: [],
        onOpen,
        onChange,
      }}
    />,
  );

  return { input: screen.getByRole("textbox"), onChange, onOpen };
}

describe("Sender skill mentions", () => {
  afterEach(cleanup);

  it("does not select a mention when Enter commits an IME composition", () => {
    const { input, onChange } = renderSender();

    fireEvent.change(input, { target: { value: "@br" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });

    expect(onChange).not.toHaveBeenCalled();
    expect(input).toHaveValue("@br");
  });

  it("uses the shared accessible menu and shows its no-match state", () => {
    const { input, onOpen } = renderSender();

    fireEvent.change(input, { target: { value: "@missing" } });

    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("group", { name: "可用技能" })).toBeInTheDocument();
    expect(screen.getByText("未找到匹配的技能")).toBeInTheDocument();
  });

  it("selects matching mentions by click and Enter", () => {
    const clickSender = renderSender();

    fireEvent.change(clickSender.input, { target: { value: "请用 @br" } });
    fireEvent.click(screen.getByRole("button", { name: /browser/ }));

    expect(clickSender.onOpen).toHaveBeenCalledTimes(1);
    expect(clickSender.onChange).toHaveBeenCalledWith(["browser"]);
    expect(clickSender.input).toHaveValue("请用  ");

    cleanup();
    const enterSender = renderSender();
    fireEvent.change(enterSender.input, { target: { value: "@BU" } });
    fireEvent.keyDown(enterSender.input, { key: "Enter" });

    expect(enterSender.onOpen).toHaveBeenCalledTimes(1);
    expect(enterSender.onChange).toHaveBeenCalledWith(["Build"]);
    expect(enterSender.input).toHaveValue(" ");
  });
});
