import { fireEvent, render, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CollapsedToolbar from ".";

describe("CollapsedToolbar", () => {
  it("keeps new-chat, task, and history actions", () => {
    const onIconClick = vi.fn();
    const onNewChat = vi.fn();
    const { container } = render(
      <CollapsedToolbar
        activePanel={null}
        onIconClick={onIconClick}
        onNewChat={onNewChat}
      />,
    );
    const view = within(container);

    view.getAllByRole("button").forEach((button) => {
      expect(button.querySelector("svg")).toHaveAttribute("width", "18");
      expect(button.querySelector("svg")).toHaveAttribute("height", "18");
    });

    fireEvent.click(view.getByRole("button", { name: "新建聊天" }));
    fireEvent.click(view.getByRole("button", { name: "我的任务" }));
    fireEvent.click(view.getByRole("button", { name: "历史记录" }));

    expect(onNewChat).toHaveBeenCalledTimes(1);
    expect(onIconClick).toHaveBeenNthCalledWith(1, "tasks");
    expect(onIconClick).toHaveBeenNthCalledWith(2, "history");
  });
});
