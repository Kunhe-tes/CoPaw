import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CapabilityGrid } from "./CapabilityGrid";

const summaries = [
  {
    id: "conversation" as const,
    title: "对话与执行",
    description: "任务进度与系统提示词的可见体验。",
    state: "unsaved" as const,
    sourceLabel: "采用默认值",
    summary: "1 段提示词",
  },
];

describe("CapabilityGrid", () => {
  it("filters by state and selects a capability card", () => {
    const onFilterChange = vi.fn();
    const onSelect = vi.fn();

    render(
      <CapabilityGrid
        summaries={summaries}
        filter="all"
        onFilterChange={onFilterChange}
        onSelect={onSelect}
      />,
    );

    fireEvent.click(screen.getByRole("radio", { name: "有未保存修改" }));
    fireEvent.click(
      screen.getByRole("button", {
        name: /对话与执行.*任务进度与系统提示词的可见体验/,
      }),
    );

    expect(onFilterChange).toHaveBeenCalledWith("unsaved");
    expect(onSelect).toHaveBeenCalledWith("conversation");
  });
});
