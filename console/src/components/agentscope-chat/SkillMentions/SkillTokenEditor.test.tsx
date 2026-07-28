import React, { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SkillTokenEditor } from "./SkillTokenEditor";
import type { SkillMentionItem } from "./useSkillMentions";

const items: SkillMentionItem[] = [
  {
    id: "skill:browser",
    type: "skill",
    label: "browser",
    name: "browser",
    description: "Use a browser",
  },
  {
    id: 'mcp_tool:["docs","search"]',
    type: "mcp_tool",
    label: "docs / search",
    server: "docs",
    name: "search",
    description: "Search docs",
  },
  {
    id: "workspace_file:media/report.pdf",
    type: "workspace_file",
    label: "report.pdf",
    root: "media",
    relative_path: "report.pdf",
    description: "media/report.pdf",
  },
  {
    id: "workspace_file:media/report file.pdf",
    type: "workspace_file",
    label: "report file.pdf",
    root: "media",
    relative_path: "report file.pdf",
    description: "media/report file.pdf",
  },
];

function ControlledTokenEditor() {
  const [selected, setSelected] = useState<SkillMentionItem[]>([]);
  const [value, setValue] = useState("");
  return (
    <SkillTokenEditor
      aria-label="消息"
      value={value}
      skillMentions={{
        items,
        selected,
        onChange: setSelected,
        onOpen: () => undefined,
      }}
      onValueChange={setValue}
    />
  );
}

function SelectedTokenEditor() {
  const [selected, setSelected] = useState<SkillMentionItem[]>([items[1]]);
  const [value, setValue] = useState("@docs/search ");
  return (
    <SkillTokenEditor
      aria-label="消息"
      value={value}
      skillMentions={{
        items,
        selected,
        onChange: setSelected,
        onOpen: () => undefined,
      }}
      onValueChange={setValue}
    />
  );
}

describe("SkillTokenEditor", () => {
  afterEach(cleanup);
  it("renders typed references as atomic tokens", () => {
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="请看 @report.pdf "
        skillMentions={{
          items,
          selected: [items[2]],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    const token = screen.getByText("@report.pdf");
    expect(token).toHaveAttribute("contenteditable", "false");
    expect(token).toHaveAttribute("data-reference-type", "workspace_file");
  });
  it("renders one distinguishable atomic token for every reference type", () => {
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="@browser @docs/search @report.pdf "
        skillMentions={{
          items,
          selected: [items[0], items[1], items[2]],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    const tokens = document.querySelectorAll("[data-skill-token=true]");
    expect(tokens).toHaveLength(3);
    expect(tokens[0]).toHaveAttribute("data-reference-type", "skill");
    expect(tokens[1]).toHaveAttribute("data-reference-type", "mcp_tool");
    expect(tokens[2]).toHaveAttribute("data-reference-type", "workspace_file");
  });
  it("uses a named icon instead of a dot before an MCP token", () => {
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="@docs/search "
        skillMentions={{
          items,
          selected: [items[1]],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("img", { name: "MCP 工具" })).toBeInTheDocument();
  });
  it("keeps a token icon out of editor text while ordinary text is entered", () => {
    render(<SelectedTokenEditor />);
    const editor = screen.getByRole("textbox", { name: "消息" });
    expect(editor.textContent).toBe("@docs/search ");

    editor.append(document.createTextNode("后续文本"));
    fireEvent.input(editor);

    expect(editor).toHaveTextContent("@docs/search 后续文本");
    expect(document.querySelectorAll("[data-skill-token=true]")).toHaveLength(
      1,
    );
  });
  it("keeps a file name containing spaces as one atomic token", () => {
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="请看 @report file.pdf "
        skillMentions={{
          items,
          selected: [items[3]],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    expect(screen.getByText("@report file.pdf")).toHaveAttribute(
      "contenteditable",
      "false",
    );
  });
  it("renders tokens in text order when a later selection was inserted before an earlier one", () => {
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="@report.pdf @browser "
        skillMentions={{
          items,
          selected: [items[0], items[2]],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    expect(document.querySelectorAll("[data-skill-token=true]")).toHaveLength(
      2,
    );
  });
  it("removes a typed token with Backspace", () => {
    const onChange = vi.fn();
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="@browser "
        skillMentions={{
          items,
          selected: [items[0]],
          onChange,
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );
    const editor = screen.getByRole("textbox", { name: "消息" });
    const range = document.createRange();
    range.setStart(editor.lastChild!, 0);
    range.collapse(true);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    fireEvent.keyDown(editor, { key: "Backspace" });
    expect(onChange).toHaveBeenCalledWith([]);
  });
  it("keeps keyboard selection and focus after Enter", () => {
    render(<ControlledTokenEditor />);
    const editor = screen.getByRole("textbox", { name: "消息" });
    editor.focus();
    editor.textContent = "@";
    const range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(false);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    fireEvent.input(editor);
    expect(editor).toHaveAttribute("aria-controls", "context-reference-menu");
    expect(editor).toHaveAttribute("aria-haspopup", "listbox");
    expect(editor).toHaveAttribute(
      "aria-activedescendant",
      "context-reference-option-skill%3Abrowser",
    );
    fireEvent.keyDown(editor, { key: "Enter" });
    expect(document.activeElement).toBe(editor);
    expect(screen.getByText("@browser")).toBeInTheDocument();
  });
  it("restores editor focus after a clicked option took focus", () => {
    render(<ControlledTokenEditor />);
    const editor = screen.getByRole("textbox", { name: "消息" });
    editor.focus();
    editor.textContent = "@";
    const range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(false);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    fireEvent.input(editor);
    const option = screen.getByRole("option", { name: /^browser/ });
    option.focus();
    fireEvent.click(option);

    expect(document.activeElement).toBe(editor);
  });
});
