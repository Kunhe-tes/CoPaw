import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { QuestionTooltip } from "./QuestionTooltip";

describe("QuestionTooltip", () => {
  it("renders outside masked quick navigation ancestors", () => {
    const { container } = render(
      <div className="conversation-quick-nav__scroll--fade-bottom">
        <QuestionTooltip
          index={3}
          text="不会被虚化区域遮住的问题"
          visible
          position={{ top: 240, right: 48 }}
        />
      </div>,
    );

    const tooltip = screen
      .getByText("不会被虚化区域遮住的问题")
      .closest<HTMLElement>(".quick-nav-tooltip");

    expect(tooltip).toBeInTheDocument();
    expect(container).not.toContainElement(tooltip);
    expect(document.body).toContainElement(tooltip);
    expect(tooltip).toHaveClass("quick-nav-tooltip--visible");
    expect(tooltip).toHaveStyle({ top: "240px", right: "48px" });
  });
});
