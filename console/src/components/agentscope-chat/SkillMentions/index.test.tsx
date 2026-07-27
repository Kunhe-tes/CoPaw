import React, { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  SkillMentionMenu,
  SkillMentionTags,
} from "./index";
import { useSkillMentions, type SkillMentionItem } from "./useSkillMentions";

const items: SkillMentionItem[] = [
  { name: "browser", description: "Use a browser" },
  { name: "Build", description: "Build an app" },
];

function MentionHarness({
  initialSelected = [],
  onOpen = vi.fn(),
  onChange = vi.fn(),
}: {
  initialSelected?: string[];
  onOpen?: () => void;
  onChange?: (names: string[]) => void;
}) {
  const [value, setValue] = useState("");
  const [selected, setSelected] = useState(initialSelected);
  const mentions = useSkillMentions({
    items,
    selected,
    onOpen,
    onChange: (names) => {
      setSelected(names);
      onChange(names);
    },
    value,
    onValueChange: setValue,
  });

  return (
    <>
      <SkillMentionTags selected={selected} onRemove={mentions.remove} />
      <textarea
        aria-label="消息"
        value={value}
        onChange={(event) => mentions.handleInputValueChange(event.target.value)}
        onKeyDown={mentions.handleKeyDown}
      />
      <output aria-label="输入值">{value}</output>
      <SkillMentionMenu
        open={mentions.open}
        items={mentions.filteredItems}
        loading={mentions.loading}
        onSelect={mentions.select}
      />
    </>
  );
}

describe("SkillMentions", () => {
  afterEach(cleanup);

  it("opens once for a trailing whitespace-boundary mention and selects the first match with Enter", () => {
    const onOpen = vi.fn();
    const onChange = vi.fn();
    render(<MentionHarness onOpen={onOpen} onChange={onChange} />);

    const input = screen.getByRole("textbox", { name: "消息" });
    fireEvent.change(input, { target: { value: "请用 @b" } });
    fireEvent.change(input, { target: { value: "请用 @br" } });

    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("group", { name: "可用技能" })).toBeInTheDocument();

    fireEvent.keyDown(input, { key: "Enter" });

    expect(onChange).toHaveBeenCalledWith(["browser"]);
    expect(screen.getByRole("status", { name: "输入值" }).textContent).toBe(
      "请用  ",
    );
    expect(screen.queryByRole("group", { name: "可用技能" })).not.toBeInTheDocument();
  });

  it("selects a clicked case-insensitive match", () => {
    const onChange = vi.fn();
    render(<MentionHarness onChange={onChange} />);

    fireEvent.change(screen.getByRole("textbox", { name: "消息" }), {
      target: { value: "@BU" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Build/ }));

    expect(onChange).toHaveBeenCalledWith(["Build"]);
    expect(screen.getByRole("status", { name: "输入值" }).textContent).toBe(" ");
  });

  it("does not open for an embedded at-sign and closes on Escape", () => {
    const onOpen = vi.fn();
    render(<MentionHarness onOpen={onOpen} />);

    const input = screen.getByRole("textbox", { name: "消息" });
    fireEvent.change(input, { target: { value: "email@browser" } });

    expect(onOpen).not.toHaveBeenCalled();
    expect(screen.queryByRole("group", { name: "可用技能" })).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: " @" } });
    expect(screen.getByRole("group", { name: "可用技能" })).toBeInTheDocument();

    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("group", { name: "可用技能" })).not.toBeInTheDocument();
  });

  it("does not select a skill when Enter is an IME composition commit", () => {
    const onChange = vi.fn();
    render(<MentionHarness onChange={onChange} />);

    const input = screen.getByRole("textbox", { name: "消息" });
    fireEvent.change(input, { target: { value: "@br" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("status", { name: "输入值" }).textContent).toBe(
      "@br",
    );
    expect(screen.getByRole("group", { name: "可用技能" })).toBeInTheDocument();
  });

  it("removes selected tags by their index", () => {
    const onChange = vi.fn();
    render(
      <MentionHarness initialSelected={["browser", "browser"]} onChange={onChange} />,
    );

    fireEvent.click(screen.getAllByLabelText("Close")[1]);

    expect(onChange).toHaveBeenCalledWith(["browser"]);
  });
});
