import React, { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SkillTokenEditor } from "./SkillTokenEditor";

const items = [
  { name: "browser", description: "Use a browser" },
  { name: "Build", description: "Build an app" },
];

function ControlledTokenEditor({
  initialValue = "",
}: {
  initialValue?: string;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [value, setValue] = useState(initialValue);

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

  it("renders a selected skill as an atomic inline token and serializes its text", () => {
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="请用 @browser "
        skillMentions={{
          items,
          selected: ["browser"],
          onChange: vi.fn(),
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );

    const token = screen.getByText("@browser");
    expect(token).toHaveAttribute("contenteditable", "false");
    expect(screen.getByRole("textbox", { name: "消息" }).textContent).toBe(
      "请用 @browser ",
    );
  });

  it("removes the adjacent token and its matching selected occurrence with Backspace", () => {
    const onChange = vi.fn();
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="@browser "
        skillMentions={{
          items,
          selected: ["browser"],
          onChange,
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );

    const editor = screen.getByRole("textbox", { name: "消息" });
    const range = document.createRange();
    range.setStart(editor, 1);
    range.collapse(true);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);

    fireEvent.keyDown(editor, { key: "Backspace" });

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("removes a token when Backspace reaches it from the following text node", () => {
    const onChange = vi.fn();
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="@browser "
        skillMentions={{
          items,
          selected: ["browser"],
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
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);

    fireEvent.keyDown(editor, { key: "Backspace" });

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("removes an immediately preceding token when the caret follows its trailing space", () => {
    const onChange = vi.fn();
    const onValueChange = vi.fn();
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="@browser "
        skillMentions={{
          items,
          selected: ["browser"],
          onChange,
          onOpen: vi.fn(),
        }}
        onValueChange={onValueChange}
      />,
    );

    const editor = screen.getByRole("textbox", { name: "消息" });
    const range = document.createRange();
    range.setStart(editor.lastChild!, 1);
    range.collapse(true);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);

    fireEvent.keyDown(editor, { key: "Backspace" });

    expect(onChange).toHaveBeenCalledWith([]);
    expect(onValueChange).toHaveBeenCalledWith("");
  });

  it("keeps composed Chinese text intact until IME composition ends", () => {
    render(<ControlledTokenEditor />);

    const editor = screen.getByRole("textbox", { name: "消息" });
    fireEvent.compositionStart(editor);
    editor.textContent = "中文";
    fireEvent.input(editor);

    expect(editor.textContent).toBe("中文");
    fireEvent.compositionEnd(editor);
    expect(editor.textContent).toBe("中文");
  });

  it("moves the active skill row with ArrowDown while the panel is open", () => {
    render(<ControlledTokenEditor />);

    const editor = screen.getByRole("textbox", { name: "消息" });
    editor.textContent = "@";
    fireEvent.input(editor);
    fireEvent.keyDown(editor, { key: "ArrowDown" });

    expect(screen.getByRole("option", { name: /browser/ })).toHaveAttribute(
      "aria-selected",
      "false",
    );
    expect(screen.getByRole("option", { name: /Build/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("synchronizes structured selection after a native token deletion", () => {
    const onChange = vi.fn();
    render(
      <SkillTokenEditor
        aria-label="消息"
        value="@browser "
        skillMentions={{
          items,
          selected: ["browser"],
          onChange,
          onOpen: vi.fn(),
        }}
        onValueChange={vi.fn()}
      />,
    );

    const editor = screen.getByRole("textbox", { name: "消息" });
    editor.replaceChildren(document.createTextNode(""));
    fireEvent.input(editor);

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("keeps typed @ text as plain prompt content until the user confirms a skill", () => {
    const onChange = vi.fn();
    const onValueChange = vi.fn();
    render(
      <SkillTokenEditor
        aria-label="消息"
        value=""
        skillMentions={{
          items,
          selected: [],
          onChange,
          onOpen: vi.fn(),
        }}
        onValueChange={onValueChange}
      />,
    );

    const editor = screen.getByRole("textbox", { name: "消息" });
    editor.textContent = "@browser";
    fireEvent.input(editor);

    expect(onValueChange).toHaveBeenCalledWith("@browser");
    expect(onChange).not.toHaveBeenCalled();
    expect(
      screen.getByRole("listbox", { name: "可用技能" }),
    ).toBeInTheDocument();
  });

  it("closes the panel when clicking outside the editor and panel boundary", () => {
    render(
      <>
        <SkillTokenEditor
          aria-label="消息"
          value="@"
          skillMentions={{
            items,
            selected: [],
            onChange: vi.fn(),
            onOpen: vi.fn(),
          }}
          onValueChange={vi.fn()}
        />
        <button type="button">outside</button>
      </>,
    );

    const editor = screen.getByRole("textbox", { name: "消息" });
    fireEvent.input(editor);
    expect(
      screen.getByRole("listbox", { name: "可用技能" }),
    ).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("button", { name: "outside" }));

    expect(screen.queryByRole("listbox", { name: "可用技能" })).toBeNull();
  });
});
