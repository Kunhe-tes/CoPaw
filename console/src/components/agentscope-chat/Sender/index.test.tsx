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

function setTokenEditorValue(input: HTMLElement, value: string) {
  input.textContent = value;
  fireEvent.input(input);
}

describe("Sender skill mentions", () => {
  afterEach(cleanup);

  it("does not select a mention when Enter commits an IME composition", () => {
    const { input, onChange } = renderSender();

    setTokenEditorValue(input, "@br");
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });

    expect(onChange).not.toHaveBeenCalled();
    expect(input).toHaveTextContent("@br");
  });

  it("uses the shared accessible menu and shows its no-match state", () => {
    const { input, onOpen } = renderSender();

    setTokenEditorValue(input, "@missing");

    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("listbox", { name: "可用技能" }),
    ).toBeInTheDocument();
    expect(screen.getByText("未找到匹配的技能")).toBeInTheDocument();
  });

  it("submits an unmatched mention when Enter cannot select a skill", () => {
    const onSubmit = vi.fn();
    render(
      <Sender
        onSubmit={onSubmit}
        skillMentions={{
          items: skills,
          selected: [],
          onOpen: vi.fn(),
          onChange: vi.fn(),
        }}
      />,
    );

    const input = screen.getByRole("textbox");
    setTokenEditorValue(input, "@missing");
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith("@missing");
    expect(input).toHaveTextContent("@missing");
  });

  it("selects a matching skill instead of submitting on Enter", () => {
    const onChange = vi.fn();
    const onSubmit = vi.fn();
    render(
      <Sender
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
    setTokenEditorValue(input, "@br");
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onChange).toHaveBeenCalledWith(["browser"]);
    expect(onSubmit).not.toHaveBeenCalled();
    expect(input.textContent).toBe("@browser ");
  });

  it("does not submit while a loading skill menu has no matches", () => {
    const onSubmit = vi.fn();
    render(
      <Sender
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
    setTokenEditorValue(input, "@missing");
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onSubmit).not.toHaveBeenCalled();
    expect(input).toHaveTextContent("@missing");
  });

  it("selects matching mentions by click and Enter", () => {
    const clickSender = renderSender();

    setTokenEditorValue(clickSender.input, "请用 @br");
    fireEvent.click(screen.getByRole("option", { name: /browser/ }));

    expect(clickSender.onOpen).toHaveBeenCalledTimes(1);
    expect(clickSender.onChange).toHaveBeenCalledWith(["browser"]);
    expect(clickSender.input.textContent).toBe("请用 @browser ");

    cleanup();
    const enterSender = renderSender();
    setTokenEditorValue(enterSender.input, "@BU");
    fireEvent.keyDown(enterSender.input, { key: "Enter" });

    expect(enterSender.onOpen).toHaveBeenCalledTimes(1);
    expect(enterSender.onChange).toHaveBeenCalledWith(["Build"]);
    expect(enterSender.input.textContent).toBe("@Build ");
  });

  it("does not activate slash-command suggestions while skill tags are enabled", () => {
    render(
      <Sender
        suggestions={[{ label: "Help", value: "help" }]}
        skillMentions={{
          items: skills,
          selected: [],
          onOpen: vi.fn(),
          onChange: vi.fn(),
        }}
      />,
    );

    const input = screen.getByRole("textbox");
    setTokenEditorValue(input, "/help @");

    expect(screen.queryByText("Help")).toBeNull();
    expect(
      screen.getByRole("listbox", { name: "可用技能" }),
    ).toBeInTheDocument();
  });
});
