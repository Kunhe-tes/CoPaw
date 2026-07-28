import React, { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SkillMentionMenu } from "./index";
import { useSkillMentions, type SkillMentionItem } from "./useSkillMentions";

const items: SkillMentionItem[] = [
  { id: "skill:browser", type: "skill", label: "browser", name: "browser", description: "Use a browser" },
  { id: 'mcp_tool:["docs","search"]', type: "mcp_tool", label: "docs / search", server: "docs", name: "search", description: "Search docs" },
  { id: "workspace_file:media/report.pdf", type: "workspace_file", label: "report.pdf", root: "media", relative_path: "report.pdf", description: "media/report.pdf" },
];

function MentionHarness({ onOpen = vi.fn(), onChange = vi.fn() }: { onOpen?: (query: string) => void; onChange?: (entries: SkillMentionItem[]) => void }) {
  const [value, setValue] = useState("");
  const [selected, setSelected] = useState<SkillMentionItem[]>([]);
  const mentions = useSkillMentions({ items, selected, onOpen, onChange: (entries) => { setSelected(entries); onChange(entries); }, value, onValueChange: setValue });
  return <><textarea aria-label="消息" value={value} onChange={(event) => mentions.handleInputValueChange(event.target.value, event.target.selectionStart ?? event.target.value.length)} onKeyDown={mentions.handleKeyDown} /><output aria-label="输入值">{value}</output><SkillMentionMenu activeIndex={mentions.activeIndex} open={mentions.open} items={mentions.filteredItems} query={mentions.query} loading={mentions.loading} onSelect={mentions.select} /></>;
}

describe("SkillMentions", () => {
  afterEach(cleanup);

  it("groups context references in a fixed order and shows the blank-query hint", () => {
    render(<SkillMentionMenu activeIndex={0} open items={items} onSelect={vi.fn()} />);
    expect(screen.getByText("技能")).toBeInTheDocument();
    expect(screen.getByText("MCP 工具")).toBeInTheDocument();
    expect(screen.getByText("文件")).toBeInTheDocument();
    expect(screen.getByText("输入以搜索工具和文件")).toBeInTheDocument();
    expect(screen.getByRole("listbox")).toHaveStyle({ overflowX: "hidden" });
  });

  it("selects a typed item once and preserves atomic display text", () => {
    const onChange = vi.fn();
    render(<MentionHarness onChange={onChange} />);
    const input = screen.getByRole("textbox", { name: "消息" });
    fireEvent.change(input, { target: { value: "请用 @" } });
    fireEvent.click(screen.getByRole("option", { name: /docs \/ search/ }));
    expect(onChange).toHaveBeenCalledWith([items[1]]);
    expect(screen.getByRole("status", { name: "输入值" }).textContent).toBe("请用 @docs/search ");
  });

  it("keeps empty groups out of the menu and renders one unified empty state", () => {
    render(<SkillMentionMenu activeIndex={0} open items={[]} query="none" onSelect={vi.fn()} />);
    expect(screen.getByText("未找到匹配的上下文引用")).toBeInTheDocument();
    expect(screen.queryByText("技能")).toBeNull();
  });
});
